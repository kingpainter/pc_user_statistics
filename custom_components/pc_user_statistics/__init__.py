# File Name: __init__.py
# Version: 2.5.0
# Description: Main setup and coordinator for the PC User Statistics integration.
# Last Updated: March 3, 2026
#
# Changes in 2.4.1:
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
import logging
import time
from typing import Any

import aiohttp
import urllib.parse

from homeassistant.config_entries import ConfigEntry, ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
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

        # Verify InfluxDB is reachable before completing setup.
        # Raises ConfigEntryNotReady if InfluxDB is down — HA will retry automatically.
        await coordinator._async_verify_influxdb()

        await coordinator.async_config_entry_first_refresh()

        # Set up persistent store and notification manager
        from .store import NotificationStore
        from .notification_manager import NotificationManager
        store = NotificationStore(hass)
        await store.async_load()
        notification_manager = NotificationManager(hass, store)

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = coordinator
        hass.data[DOMAIN]["store"] = store
        hass.data[DOMAIN]["notification_manager"] = notification_manager

        await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

        # ── Track only the two sensors we care about ───────────────────────
        # async_track_state_change_event is far more efficient than the global
        # EVENT_STATE_CHANGED bus — HA filters at the source, not in our code.
        entry.async_on_unload(
            async_track_state_change_event(
                hass,
                [coordinator._user_entity, coordinator._watt_entity],
                coordinator._handle_state_change,
            )
        )

        # ── FIX: Removed entry.add_update_listener(_async_options_updated) ──
        # The update listener called async_reload() immediately when options
        # changed, killing the WebSocket connection before ws_save_config()
        # could send its response. Reload is now handled exclusively by
        # ws_save_config() via hass.async_create_task() after send_result().

        # Register WebSocket API and sidebar panel
        from .websocket import async_register_websocket_commands
        from .panel import async_register_panel
        async_register_websocket_commands(hass)
        await async_register_panel(hass)

        _LOGGER.info("PC User Statistics integration setup completed successfully")
        return True

    except Exception as err:
        _LOGGER.exception("Failed to set up PC User Statistics integration: %s", err)
        raise


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
            hass.data[DOMAIN].pop(entry.entry_id, None)
            _LOGGER.info("PC User Statistics integration unloaded successfully")
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
        self.monthly: dict[str, dict[str, float]] = {
            user: {"time": 0.0, "energy": 0.0, "cost": 0.0}
            for user in self.tracked_users
        }
        # Track whether initial InfluxDB load has completed
        self._monthly_loaded: bool = False

        # ── Timing ────────────────────────────────────────────────────────
        self.last_time: float = time.time()
        self.last_power: float = 0.0
        self.last_month: int = datetime.now(timezone.utc).month
        self.last_write_time: float = time.time()

        # ── Cached entity IDs — read once at init, not on every state lookup ──
        self._user_entity: str  = config_entry.data.get("user_entity",          USER_ENTITY)
        self._watt_entity: str  = config_entry.data.get("watt_entity",          WATT_ENTITY)
        self._device_entity: str = config_entry.data.get("device_power_entity", DEVICE_POWER_ENTITY)
        self._price_entity: str = config_entry.data.get("price_entity",         PRICE_ENTITY)

        # ── Write buffer for failed InfluxDB writes ────────────────────────
        self.failed_writes: list[dict] = []

        # Load monthly data in the background — does NOT block coordinator init
        hass.async_create_task(self._async_load_monthly_data())

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
        if not self._http_session.closed:
            await self._http_session.close()
            _LOGGER.debug("InfluxDB HTTP session closed")

    # ── InfluxDB helpers ───────────────────────────────────────────────────

    @property
    def _influx_base_url(self) -> str:
        return f"http://{self.config['host']}:{self.config['port']}"

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

            for user, values in parsed_data.items():
                if user in self.monthly:
                    self.monthly[user].update(values)

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
                    import asyncio
                    await asyncio.sleep(delay)
                    await self._async_load_monthly_data(retry=retry + 1)
                self.hass.async_create_task(_retry())
            else:
                _LOGGER.error(
                    "Failed to load monthly data from InfluxDB after %d attempts: %s. "
                    "Monthly totals will start from 0 and accumulate from now.",
                    max_retries, err,
                )
                # Mark as loaded with zeros so panel doesn't show spinner forever
                self._monthly_loaded = True

        except Exception as err:
            _LOGGER.exception("Unexpected error loading monthly data: %s", err)
            self._monthly_loaded = True

    # ── Coordinator update ─────────────────────────────────────────────────

    async def _async_update_data(self) -> dict[str, Any]:
        """Called by the coordinator at regular intervals."""
        now = time.time()

        # Roll over monthly totals on month change
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
            self._monthly_loaded = False
            await self._async_load_monthly_data()
            self.last_month = current_month

        # Retry any buffered writes
        if self.failed_writes:
            await self._retry_failed_writes()

        await self._calculate_deltas(now, force_write=True)

        # BUG FIX: update last_time after polling delta so the next 60s poll
        # calculates delta from NOW, not from the previous poll or state-change.
        # Without this, each poll accumulates time from an ever-growing window.
        self.last_time = now

        # Evaluate notification rules
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
            # Note: last_time is set inside _handle_user_change for user events
        elif entity_id == self._watt_entity and self.current_user:
            await self._handle_power_change(now)
            # Update last_time for power-change events
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

        # Defensive: guard against dict values that slipped through normalization
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

        if new_user != self.current_user:
            _LOGGER.info("User changed: %s → %s", self.current_user, new_user)

            if self.current_user:
                await self._calculate_deltas(now, force_write=True)

            self.current_user = new_user
            if new_user:
                self.acc_time = 0.0
                self.acc_energy = 0.0
                self.acc_cost = 0.0
                self.last_power = self._get_power()

            # BUG FIX: reset last_time HERE so the new user's first delta
            # starts from this moment — not from whenever the previous user's
            # last event was. Without this, the first _calculate_deltas call
            # for the new user inherits the old last_time and adds phantom time.
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

        if self.current_user in self.monthly:
            self.monthly[self.current_user]["time"]   += delta_time
            self.monthly[self.current_user]["energy"] += energy_delta
            self.monthly[self.current_user]["cost"]   += cost_delta

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
        timestamp_ns = int(datetime.utcnow().timestamp() * 1_000_000_000)
        point = (
            f"{MEASUREMENT},user={self.current_user} "
            f"power={power},time_delta={time_delta},"
            f"energy_delta={energy_delta},cost_delta={cost_delta} "
            f"{timestamp_ns}"
        )
        success = await self._write_point_to_influx(point)
        if not success:
            self._buffer_failed_write({"point": point, "timestamp": timestamp_ns, "attempts": 1})

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
        return {
            "current_user":   self.current_user,
            "acc_time":       self.acc_time,
            "acc_energy":     self.acc_energy,
            "acc_cost":       self.acc_cost,
            "monthly":        self.monthly,
            "monthly_loaded": self._monthly_loaded,
        }
