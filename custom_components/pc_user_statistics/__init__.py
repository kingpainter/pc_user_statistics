# File Name: __init__.py
# Version: 2.7.4
# Description: Main setup and coordinator for the PC User Statistics integration.
# Last Updated: May 15, 2026
#
# Changes in 2.7.4:
#   FIX: last_write_time initialised to 0.0 instead of time.time().
#        system_health.py uses last_write_time > 0 to detect whether a real
#        write has occurred. Initialising to time.time() made health always
#        show a recent (fake) write time on startup, hiding the "aldrig" state.
#        Now correctly shows "aldrig" until the first successful InfluxDB write.
#
# Changes in 2.7.3:
#   FIX 1: Session snapshot now flushed to disk on EVERY successful InfluxDB write.
#           Previously save_session_in_memory() was called but async_flush_session()
#           was not — the snapshot only reached disk if a notification rule fired
#           (notification_manager.async_flush() is conditional on any_sent).
#           In practice: no notifications = session never persisted = data loss on restart.
#
#   FIX 2: Removed force_write=True from coordinator poll (_async_update_data).
#           force_write bypassed the WRITE_THRESHOLD guard. Combined with the
#           state-change handler also able to trigger writes, this caused double
#           writes within the same 60s window → double-counting in InfluxDB.
#           Coordinator poll now uses force_write=False (default). The 60s
#           WRITE_THRESHOLD in _calculate_deltas is the single source of truth.
#
# Changes in 2.7.2:
#   FIX: Session snapshot now saved immediately on user login.
#        Previously the first snapshot was written ~60s after login
#        (on the first InfluxDB write). If HA restarted within those
#        60s, current_user was not recoverable. One extra disk write
#        at login closes this gap — max data loss is now ~0s at login.
#
# Changes in 2.7.1:
#   FIX 1: Session snapshot now saved to disk even when InfluxDB write fails.
#           Previously, if InfluxDB was unreachable, no snapshot was written
#           and acc_time was lost on HA restart. Now uses async_flush_session()
#           for an immediate disk write in the failure path.
#
#   FIX 2: _async_restore_session() now receives the store instance directly
#           from async_setup_entry instead of fetching it from hass.data via
#           asyncio.sleep(0). Eliminates timing fragility at startup.
#   NEW: Session persistence — survives HA restart mid-session.
#        Session state (current_user, acc_time, acc_energy, acc_cost, last_time)
#        is saved to disk on every successful InfluxDB write (~every 60s) and
#        restored at HA startup. Max data loss on HA restart: ~60s.
#        New method: _async_restore_session()
#        Logout clears the snapshot so stale sessions are never restored.
#
# Changes in 2.6.2:
#   FIX: Removed entry.add_update_listener(_async_options_updated).
#        The listener triggered an immediate async_reload() whenever options were
#        updated, which unloaded the integration while ws_save_config() was still
#        waiting to send its WebSocket response. This caused a silent crash:
#        the panel froze, data was not saved, and only a full HA restart helped.
#
#        Integration reload is now triggered exclusively by ws_save_config() via
#        hass.async_create_task(_do_reload()), which runs AFTER send_result() has
#        been delivered to the browser. This guarantees the WS round-trip completes
#        before the coordinator is torn down.

from datetime import datetime, timedelta, timezone
import asyncio
import logging
import time
from typing import Any

import aiohttp
import urllib.parse

from homeassistant.config_entries import ConfigEntry, ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    DOMAIN,
    USER_ENTITY,
    WATT_ENTITY,
    DEVICE_POWER_ENTITY,
    PRICE_ENTITY,
    MEASUREMENT,
    UPDATE_INTERVAL,
    WRITE_THRESHOLD,
    MAX_BUFFERED_WRITES,
    MAX_RETRY_ATTEMPTS,
    CONF_USER_MAPPINGS,
    CONF_TRACKED_USERS,
    DEFAULT_USER_MAP,
    DEFAULT_USERS,
)
from .helpers import safe_float_from_state, parse_influxdb_response
from .store import NotificationStore
from .notification_manager import NotificationManager

_LOGGER = logging.getLogger(__name__)


def _normalize_user_map(raw: dict) -> dict[str, str]:
    """
    Normalize user_map values to plain strings.

    The config UI (ws_save_config) may store values as dicts when an HA user
    is linked, e.g. {'user_id': 'lukas', 'ha_user': 'da88c1c...'}.
    The coordinator only needs the user_id string for session tracking.
    """
    normalized: dict[str, str] = {}
    for sensor_state, value in raw.items():
        if isinstance(value, dict):
            user_id = value.get("user_id", "")
            if user_id:
                normalized[sensor_state] = str(user_id).lower()
            else:
                _LOGGER.warning(
                    "user_map entry '%s' is a dict without 'user_id', skipping: %s",
                    sensor_state, value,
                )
        elif isinstance(value, str) and value:
            normalized[sensor_state] = value.lower()
        else:
            _LOGGER.warning(
                "user_map entry '%s' has unexpected value type %s, skipping: %s",
                sensor_state, type(value).__name__, value,
            )
    return normalized


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PC User Statistics from a config entry."""
    _LOGGER.info("Setting up PC User Statistics integration (entry: %s)", entry.entry_id)

    try:
        coordinator = PCStatisticsCoordinator(hass, entry)
        store = NotificationStore(hass)

        # Verify InfluxDB connectivity and load persistent store in parallel.
        # The two are completely independent — no reason to run them serially.
        await asyncio.gather(
            coordinator._async_verify_influxdb(),
            store.async_load(),
        )

        await coordinator.async_config_entry_first_refresh()

        notification_manager = NotificationManager(hass, store)

        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
        hass.data[DOMAIN]["store"] = store
        hass.data[DOMAIN]["notification_manager"] = notification_manager

        await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

        entry.async_on_unload(
            async_track_state_change_event(
                hass,
                [coordinator._user_entity, coordinator._watt_entity],
                coordinator._handle_state_change,
            )
        )

        # Restore persisted session — called here with store directly to avoid
        # timing dependency on hass.data population order.
        await coordinator._async_restore_session(store)

        # Read the current user sensor state at startup.
        # async_track_state_change_event only fires on *future* changes — if HA restarts
        # while a user is already logged in, the sensor never fires again and current_user
        # stays None, silently discarding all playtime until the next login event.
        initial_user_state = hass.states.get(coordinator._user_entity)
        if initial_user_state and initial_user_state.state not in (
            "unavailable", "unknown", "none", "",
        ):
            user_key = initial_user_state.state.lower()
            raw_mapped = coordinator.user_map.get(user_key)
            if isinstance(raw_mapped, dict):
                initial_user = raw_mapped.get("user_id") or None
            elif isinstance(raw_mapped, str) and raw_mapped:
                initial_user = raw_mapped
            else:
                initial_user = None
            if initial_user:
                coordinator.current_user = initial_user
                coordinator.last_time = time.time()
                coordinator.last_power = coordinator._get_power()
                _LOGGER.info(
                    "Startup: '%s' already logged in — resuming session tracking",
                    initial_user,
                )

        from .websocket import async_register_websocket_commands
        from .panel import async_register_panel
        async_register_websocket_commands(hass)
        await async_register_panel(hass)

        _LOGGER.info("PC User Statistics setup completed successfully")
        return True

    except (ConfigEntryAuthFailed, ConfigEntryNotReady):
        raise
    except Exception as err:
        _LOGGER.exception("Unexpected error setting up PC User Statistics: %s", err)
        raise ConfigEntryNotReady(f"Unexpected setup error: {err}") from err


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading PC User Statistics integration (entry: %s)", entry.entry_id)

    try:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
        if unload_ok:
            coordinator: PCStatisticsCoordinator = hass.data[DOMAIN].get(entry.entry_id)
            if coordinator:
                await coordinator.async_shutdown()

            from .panel import async_unregister_panel, async_unregister_cards_resource
            async_unregister_panel(hass)
            await async_unregister_cards_resource(hass)

            # Remove all DOMAIN keys — prevents stale store/notification_manager
            # references leaking into the next reload cycle
            domain_data = hass.data.get(DOMAIN, {})
            domain_data.pop(entry.entry_id, None)
            domain_data.pop("store", None)
            domain_data.pop("notification_manager", None)

            _LOGGER.info("PC User Statistics unloaded successfully")
        return unload_ok

    except Exception as err:
        _LOGGER.exception("Failed to unload PC User Statistics integration: %s", err)
        return False


class PCStatisticsCoordinator(DataUpdateCoordinator):
    """Coordinator for fetching and managing PC statistics data."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.config_entry = config_entry
        self.config = config_entry.data

        # ── Persistent HTTP session ────────────────────────────────────────
        # One session reused for all InfluxDB writes and queries.
        # Connector is closed explicitly in async_shutdown().
        self._http_session: aiohttp.ClientSession = aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(
                config_entry.data["username"],
                config_entry.data["password"],
            ),
            timeout=aiohttp.ClientTimeout(total=5),
        )

        # ── User configuration ─────────────────────────────────────────────
        raw_map = config_entry.options.get(CONF_USER_MAPPINGS, dict(DEFAULT_USER_MAP))
        self.user_map: dict[str, str] = _normalize_user_map(raw_map)
        self.tracked_users: list[str] = config_entry.options.get(
            CONF_TRACKED_USERS, list(DEFAULT_USERS)
        )
        _LOGGER.info(
            "User configuration loaded — tracked: %s, mappings: %s",
            self.tracked_users, self.user_map,
        )

        # ── Session tracking ───────────────────────────────────────────────
        self.current_user: str | None = None
        self.acc_time: float = 0.0
        self.acc_energy: float = 0.0
        self.acc_cost: float = 0.0

        # ── Monthly totals (in-memory, loaded from InfluxDB at startup) ────
        # IMPORTANT: Do NOT accumulate deltas directly into self.monthly until
        # _async_load_monthly_data() completes. Until then, all deltas go into
        # self._pending, which is merged into self.monthly after the InfluxDB
        # load. This prevents double-counting: if a delta is written to InfluxDB
        # before the load completes, it would appear in both the InfluxDB SUM
        # and self.monthly if we accumulated there directly.
        self.monthly: dict[str, dict[str, float]] = {
            user: {"time": 0.0, "energy": 0.0, "cost": 0.0}
            for user in self.tracked_users
        }
        self._pending: dict[str, dict[str, float]] = {
            user: {"time": 0.0, "energy": 0.0, "cost": 0.0}
            for user in self.tracked_users
        }
        # True once _async_load_monthly_data() has successfully set self.monthly
        self._monthly_loaded: bool = False

        # ── Timing ────────────────────────────────────────────────────────
        self.last_time: float = time.time()
        self.last_power: float = 0.0
        self.last_month: int = datetime.now(timezone.utc).month
        # FIX v2.7.4: initialised to 0.0 (not time.time()) so system_health
        # correctly shows "aldrig" until the first real InfluxDB write occurs.
        self.last_write_time: float = 0.0

        # ── Cached entity IDs — read once at init, not on every state lookup ──
        self._user_entity: str   = config_entry.data.get("user_entity",          USER_ENTITY)
        self._watt_entity: str   = config_entry.data.get("watt_entity",          WATT_ENTITY)
        self._device_entity: str = config_entry.data.get("device_power_entity",  DEVICE_POWER_ENTITY)
        self._price_entity: str  = config_entry.data.get("price_entity",         PRICE_ENTITY)

        # Cache base URL — built once, reused for every InfluxDB request
        self._influx_base_url: str = (
            f"http://{config_entry.data['host']}:{config_entry.data['port']}"
        )

        # ── Write buffer for failed InfluxDB writes ────────────────────────
        self.failed_writes: list[dict] = []

        # Repair issue tracking — raised after consecutive InfluxDB write failures
        self._consecutive_write_failures: int = 0
        self._REPAIR_THRESHOLD: int = 5

        # Guard: prevents background retry tasks from running after unload
        self._unloaded: bool = False

        # Idle tracking: set when user logs out, cleared when user logs in.
        # Used by idle_pc notification rule as the correct idle duration source.
        self._idle_since: float | None = None

        # Load monthly data in the background — does NOT block coordinator init
        hass.async_create_task(self._async_load_monthly_data())
        # _async_restore_session is called explicitly from async_setup_entry
        # with the store instance — avoids timing dependency on hass.data

        _LOGGER.debug("PCStatisticsCoordinator initialized (entry: %s)", config_entry.entry_id)

    async def _async_verify_influxdb(self) -> None:
        """Ping InfluxDB to verify connectivity at setup time.

        Raises ConfigEntryNotReady if unreachable (HA will retry).
        Raises ConfigEntryAuthFailed if credentials are wrong (HA prompts re-auth).
        """
        try:
            async with self._http_session.get(
                f"{self._influx_base_url}/ping",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 401:
                    raise ConfigEntryAuthFailed(
                        "InfluxDB authentication failed — check username and password"
                    )
                if resp.status != 204:
                    raise ConfigEntryNotReady(
                        f"InfluxDB ping returned unexpected status {resp.status}"
                    )
        except ConfigEntryAuthFailed:
            raise
        except ConfigEntryNotReady:
            raise
        except aiohttp.ClientError as err:
            raise ConfigEntryNotReady(
                f"Cannot connect to InfluxDB at {self._influx_base_url}: {err}"
            ) from err

    async def async_shutdown(self) -> None:
        """Close the persistent HTTP session. Called on integration unload."""
        self._unloaded = True  # Stop any pending background retry tasks
        if not self._http_session.closed:
            await self._http_session.close()
            _LOGGER.debug("InfluxDB HTTP session closed")

    # ── InfluxDB helpers ───────────────────────────────────────────────────

    async def _async_load_monthly_data(self, retry: int = 0) -> None:
        """Query InfluxDB for initial monthly sums and merge into self.monthly.

        Retries up to 3 times with exponential backoff if InfluxDB is not yet
        ready at HA startup (common when InfluxDB add-on starts after HA).
        """
        now = datetime.now(timezone.utc)
        month_start = (
            now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        )

        query = (
            f'SELECT SUM("time_delta") AS "time", '
            f'SUM("energy_delta") AS "energy", '
            f'SUM("cost_delta") AS "cost" '
            f'FROM {MEASUREMENT} '
            f"WHERE time >= '{month_start}' "
            f'GROUP BY "user"'
        )

        try:
            query_params = urllib.parse.urlencode({"q": query, "db": self.config["database"]})
            async with self._http_session.get(
                f"{self._influx_base_url}/query?{query_params}"
            ) as response:
                if response.status != 200:
                    raise aiohttp.ClientError(f"HTTP {response.status}")
                data = await response.json()

            field_mappings = {"time": 1, "energy": 2, "cost": 3}
            parsed_data = parse_influxdb_response(data, field_mappings)

            new_monthly: dict[str, dict[str, float]] = {
                user: {"time": 0.0, "energy": 0.0, "cost": 0.0}
                for user in self.tracked_users
            }
            for user, values in parsed_data.items():
                if user in new_monthly:
                    for key, val in values.items():
                        new_monthly[user][key] = float(val or 0)

            # Merge in any deltas accumulated before load completed
            for user in self.tracked_users:
                pending = self._pending.get(user, {})
                for key in ("time", "energy", "cost"):
                    new_monthly[user][key] += pending.get(key, 0.0)

            self.monthly = new_monthly
            self._pending = {}  # No longer needed — monthly is now authoritative
            self._monthly_loaded = True
            _LOGGER.info(
                "Monthly data loaded from InfluxDB: %s",
                {u: {k: round(v, 2) for k, v in vals.items()} for u, vals in self.monthly.items()},
            )

        except aiohttp.ClientError as err:
            max_retries = 3
            if retry < max_retries:
                delay = 30 * (2 ** retry)  # 30s, 60s, 120s
                _LOGGER.warning(
                    "InfluxDB not ready for monthly data load (attempt %d/%d), "
                    "retrying in %ds: %s",
                    retry + 1, max_retries, delay, err,
                )
                async def _retry():
                    await asyncio.sleep(delay)
                    if self._unloaded:
                        _LOGGER.debug("Integration unloaded — aborting monthly data retry")
                        return
                    await self._async_load_monthly_data(retry=retry + 1)
                self.hass.async_create_task(_retry())
            else:
                _LOGGER.error(
                    "Failed to load monthly data from InfluxDB after %d attempts: %s. "
                    "Monthly totals will start from 0 and accumulate from now.",
                    max_retries, err,
                )
                self._monthly_loaded = True

        except Exception as err:
            _LOGGER.exception("Unexpected error loading monthly data: %s", err)
            self._monthly_loaded = True

    async def _async_restore_session(self, store: "NotificationStore") -> None:
        """Restore in-progress session from persistent store after HA restart."""
        if not store:
            _LOGGER.debug("Session restore: store not available")
            return

        snapshot = store.get_session()
        if not snapshot:
            _LOGGER.debug("Session restore: no snapshot found")
            return

        saved_user: str | None = snapshot.get("current_user")
        saved_at: float = snapshot.get("saved_at", 0.0)
        now = time.time()
        age = now - saved_at

        if age > 4 * 3600:
            _LOGGER.info(
                "Session restore: snapshot %.0f min old — too stale, discarding",
                age / 60,
            )
            await store.async_clear_session()
            return

        if saved_user and saved_user not in self.tracked_users:
            _LOGGER.warning(
                "Session restore: user '%s' not in tracked_users — discarding",
                saved_user,
            )
            await store.async_clear_session()
            return

        try:
            sensor_state = self.hass.states.get(self._user_entity)
            if sensor_state and sensor_state.state not in ("unavailable", "unknown", "none", ""):
                live_key = sensor_state.state.lower()
                live_user = self.user_map.get(live_key)
                if live_user and live_user != saved_user:
                    _LOGGER.info(
                        "Session restore: live user '%s' ≠ snapshot user '%s' — discarding",
                        live_user, saved_user,
                    )
                    await store.async_clear_session()
                    return
        except Exception as err:
            _LOGGER.warning("Session restore: could not read user sensor: %s", err)

        self.current_user = saved_user
        self.acc_time     = snapshot.get("acc_time",   0.0)
        self.acc_energy   = snapshot.get("acc_energy", 0.0)
        self.acc_cost     = snapshot.get("acc_cost",   0.0)
        self.last_time       = now
        self.last_write_time = now

        _LOGGER.info(
            "Session restored after HA restart — user='%s' acc_time=%.0fs "
            "acc_energy=%.4fkWh acc_cost=%.4fDKK (snapshot age %.0fs)",
            self.current_user, self.acc_time, self.acc_energy, self.acc_cost, age,
        )

    # ── Coordinator update ─────────────────────────────────────────────────

    async def _async_update_data(self) -> dict[str, Any]:
        """Called by the coordinator at regular intervals."""
        now = time.time()

        current_month = datetime.now(timezone.utc).month
        if current_month != self.last_month:
            _LOGGER.info(
                "Month rolled over (%d → %d) — resetting monthly totals and reloading from InfluxDB",
                self.last_month, current_month,
            )
            self.monthly = {
                user: {"time": 0.0, "energy": 0.0, "cost": 0.0}
                for user in self.tracked_users
            }
            self._pending = {
                user: {"time": 0.0, "energy": 0.0, "cost": 0.0}
                for user in self.tracked_users
            }
            self._monthly_loaded = False
            await self._async_load_monthly_data()
            self.last_month = current_month

        if self.failed_writes:
            await self._retry_failed_writes()

        if self._monthly_loaded:
            await self._calculate_deltas(now)
            self.last_time = now
        else:
            _LOGGER.debug("Monthly data not yet loaded — skipping InfluxDB write this poll")

        try:
            nm = self.hass.data.get(DOMAIN, {}).get("notification_manager")
            if nm:
                await nm.async_evaluate(self)
        except Exception as err:
            _LOGGER.warning("Notification evaluation error: %s", err)

        return self._get_data()

    # ── State change handling ──────────────────────────────────────────────

    @callback
    def _handle_state_change(self, event) -> None:
        """Sync callback — dispatched only for the two tracked entity IDs."""
        self.hass.async_create_task(self._async_handle_state_change(event))

    async def _async_handle_state_change(self, event) -> None:
        """Async handler for user/power state changes."""
        entity_id = event.data.get("entity_id")
        now = time.time()

        if entity_id == self._user_entity:
            await self._handle_user_change(event, now)
        elif entity_id == self._watt_entity and self.current_user:
            await self._handle_power_change(now)
            self.last_time = now

        self.async_set_updated_data(self._get_data())

    async def _handle_user_change(self, event, now: float) -> None:
        """Handle user sensor state change."""
        new_state = event.data.get("new_state")

        if new_state is None or new_state.state in ("unavailable", "unknown"):
            user_key = None
        else:
            user_key = new_state.state.lower()

        raw_mapped = self.user_map.get(user_key) if user_key is not None else None

        if isinstance(raw_mapped, dict):
            _LOGGER.warning(
                "user_map returned a dict for key '%s' — normalizing on the fly: %s",
                user_key, raw_mapped,
            )
            new_user: str | None = raw_mapped.get("user_id") or None
        elif isinstance(raw_mapped, str) and raw_mapped:
            new_user = raw_mapped
        else:
            new_user = None

        same_user_relogin = (
            new_user is not None
            and new_user == self.current_user
            and (now - self.last_time) > 600
        )

        if new_user != self.current_user or same_user_relogin:
            if same_user_relogin:
                _LOGGER.info(
                    "Same-user re-login detected for '%s' (PC shut down without logout) "
                    "— starting new session, resetting accumulators",
                    new_user,
                )
            else:
                _LOGGER.info("User changed: %s → %s", self.current_user, new_user)

            if self.current_user and not same_user_relogin:
                await self._calculate_deltas(now, force_write=True)

            self.current_user = new_user
            if new_user:
                self._idle_since = None
                self.acc_time = 0.0
                self.acc_energy = 0.0
                self.acc_cost = 0.0
                self.last_power = self._get_power()

                store = self.hass.data.get(DOMAIN, {}).get("store")
                if store:
                    store.reset_session_sent(new_user)

                _store = self.hass.data.get(DOMAIN, {}).get("store")
                if _store:
                    _store.save_session_in_memory(new_user, 0.0, 0.0, 0.0, now)
                    self.hass.async_create_task(_store.async_flush_session())
            else:
                self._idle_since = now
                _store = self.hass.data.get(DOMAIN, {}).get("store")
                if _store:
                    self.hass.async_create_task(_store.async_clear_session())

            self.last_time = now
            self.last_write_time = now

    async def _handle_power_change(self, now: float) -> None:
        """Handle power sensor state change."""
        await self._calculate_deltas(now)

    # ── Delta calculation ──────────────────────────────────────────────────

    async def _calculate_deltas(self, now: float, force_write: bool = False) -> None:
        """Accumulate time/energy/cost deltas and optionally write to InfluxDB."""
        if not self.current_user:
            return

        if not isinstance(self.current_user, str):
            _LOGGER.error(
                "_calculate_deltas: current_user is not a string (%s), resetting",
                type(self.current_user).__name__,
            )
            self.current_user = None
            return

        delta_time = now - self.last_time
        if delta_time <= 0:
            _LOGGER.debug("Non-positive delta_time: %s, skipping", delta_time)
            return

        current_power = self._get_power()
        avg_power     = (current_power + self.last_power) / 2
        energy_delta  = avg_power * delta_time / 3_600_000  # W·s → kWh
        price         = self._get_price()
        cost_delta    = energy_delta * price

        self.acc_time   += delta_time
        self.acc_energy += energy_delta
        self.acc_cost   += cost_delta

        target = self.monthly if self._monthly_loaded else self._pending
        if self.current_user in target:
            target[self.current_user]["time"]   += delta_time
            target[self.current_user]["energy"] += energy_delta
            target[self.current_user]["cost"]   += cost_delta

        time_since_write = now - self.last_write_time
        if force_write or time_since_write >= WRITE_THRESHOLD:
            await self._async_write_to_influx(current_power, delta_time, energy_delta, cost_delta)
            self.last_write_time = now

        self.last_power = current_power

    # ── Sensor helpers ─────────────────────────────────────────────────────

    def _get_power(self) -> float:
        """Net PC power = watt sensor minus meter device overhead."""
        watt_state   = self.hass.states.get(self._watt_entity)
        device_state = self.hass.states.get(self._device_entity)
        watt         = safe_float_from_state(watt_state,   default=0.0, min_value=0.0)
        device_power = safe_float_from_state(device_state, default=0.0, min_value=0.0)
        return max(watt - device_power, 0.0)

    def _get_price(self) -> float:
        """Current energy price in DKK/kWh."""
        price_state = self.hass.states.get(self._price_entity)
        return safe_float_from_state(price_state, default=0.0, min_value=0.0)

    # ── InfluxDB write ─────────────────────────────────────────────────────

    async def _async_write_to_influx(
        self,
        power: float,
        time_delta: float,
        energy_delta: float,
        cost_delta: float,
    ) -> None:
        """Build line-protocol point and write to InfluxDB. Buffers on failure."""
        timestamp_ns = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)
        point = (
            f"{MEASUREMENT},user={self.current_user} "
            f"power={power},time_delta={time_delta},"
            f"energy_delta={energy_delta},cost_delta={cost_delta} "
            f"{timestamp_ns}"
        )
        success = await self._write_point_to_influx(point)
        if success:
            self._clear_repair_issue()
            self._consecutive_write_failures = 0
            _store = self.hass.data.get(DOMAIN, {}).get("store")
            if _store:
                _store.save_session_in_memory(
                    self.current_user,
                    self.acc_time,
                    self.acc_energy,
                    self.acc_cost,
                    time.time(),
                )
                self.hass.async_create_task(_store.async_flush_session())
        else:
            self._consecutive_write_failures += 1
            self._maybe_raise_repair_issue()
            self._buffer_failed_write({"point": point, "timestamp": timestamp_ns, "attempts": 1})
            _store = self.hass.data.get(DOMAIN, {}).get("store")
            if _store:
                _store.save_session_in_memory(
                    self.current_user,
                    self.acc_time,
                    self.acc_energy,
                    self.acc_cost,
                    time.time(),
                )
                self.hass.async_create_task(_store.async_flush_session())

    async def _write_point_to_influx(self, point: str) -> bool:
        """Write a single line-protocol point. Returns True on success."""
        try:
            url = f"{self._influx_base_url}/write?db={self.config['database']}"
            async with self._http_session.post(url, data=point) as response:
                if response.status == 401:
                    _LOGGER.error(
                        "InfluxDB authentication failed (401) — "
                        "update credentials via Settings → Devices & Services → PC User Statistics → Reconfigure"
                    )
                    raise ConfigEntryAuthFailed(
                        "InfluxDB authentication failed — reconfigure credentials"
                    )
                if response.status != 204:
                    _LOGGER.warning("InfluxDB write failed: HTTP %s", response.status)
                    return False
                _LOGGER.debug("InfluxDB write OK: %s", point)
                return True
        except ConfigEntryAuthFailed:
            raise
        except aiohttp.ClientError as err:
            _LOGGER.warning("InfluxDB write error: %s", err)
            return False
        except Exception as err:
            _LOGGER.exception("Unexpected InfluxDB write error: %s", err)
            return False

    def _maybe_raise_repair_issue(self) -> None:
        """Raise a HA repair issue if consecutive write failures hit threshold."""
        if self._consecutive_write_failures >= self._REPAIR_THRESHOLD:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                "influxdb_unreachable",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="influxdb_unreachable",
            )
            _LOGGER.warning(
                "InfluxDB unreachable after %d consecutive failures — repair issue raised",
                self._consecutive_write_failures,
            )

    def _clear_repair_issue(self) -> None:
        """Clear the InfluxDB repair issue when writes succeed again."""
        if self._consecutive_write_failures >= self._REPAIR_THRESHOLD:
            ir.async_delete_issue(self.hass, DOMAIN, "influxdb_unreachable")
            _LOGGER.info("InfluxDB write succeeded — repair issue cleared")

    def _buffer_failed_write(self, write_data: dict) -> None:
        """FIFO buffer for failed writes. Drops oldest when full."""
        if len(self.failed_writes) >= MAX_BUFFERED_WRITES:
            dropped = self.failed_writes.pop(0)
            _LOGGER.warning(
                "Write buffer full, dropped oldest point (ts=%s)",
                dropped.get("timestamp"),
            )
        self.failed_writes.append(write_data)
        _LOGGER.info(
            "Buffered failed write (%d/%d)",
            len(self.failed_writes), MAX_BUFFERED_WRITES,
        )

    async def _retry_failed_writes(self) -> None:
        """Retry buffered failed writes. Drops after max attempts."""
        _LOGGER.info("Retrying %d buffered write(s)", len(self.failed_writes))
        still_failing: list[dict] = []

        for write_data in self.failed_writes:
            if write_data["attempts"] >= MAX_RETRY_ATTEMPTS:
                _LOGGER.error(
                    "Max retries (%d) reached, dropping point (ts=%s)",
                    MAX_RETRY_ATTEMPTS, write_data.get("timestamp"),
                )
                continue

            write_data["attempts"] += 1
            if await self._write_point_to_influx(write_data["point"]):
                _LOGGER.info(
                    "Retry succeeded (attempt %d/%d)",
                    write_data["attempts"], MAX_RETRY_ATTEMPTS,
                )
            else:
                still_failing.append(write_data)

        self.failed_writes = still_failing

    # ── Data snapshot ──────────────────────────────────────────────────────

    def _get_data(self) -> dict[str, Any]:
        """Return current data snapshot for coordinator listeners and sensors."""
        if self._monthly_loaded:
            monthly_view = self.monthly
        else:
            monthly_view = {
                user: {
                    "time":   self.monthly[user]["time"]   + self._pending.get(user, {}).get("time", 0.0),
                    "energy": self.monthly[user]["energy"] + self._pending.get(user, {}).get("energy", 0.0),
                    "cost":   self.monthly[user]["cost"]   + self._pending.get(user, {}).get("cost", 0.0),
                }
                for user in self.tracked_users
            }

        return {
            "current_user":   self.current_user,
            "acc_time":       self.acc_time,
            "acc_energy":     self.acc_energy,
            "acc_cost":       self.acc_cost,
            "monthly":        monthly_view,
            "monthly_loaded": self._monthly_loaded,
        }
