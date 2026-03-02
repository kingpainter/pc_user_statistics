# File Name: __init__.py
# Version: 2.2.0
# Description: Main setup and coordinator for the PC User Statistics integration.
# Last Updated: March 1, 2026

from datetime import datetime, timedelta
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.const import EVENT_STATE_CHANGED
import aiohttp
import urllib.parse

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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PC User Statistics from a config entry."""
    _LOGGER.info("Setting up PC User Statistics integration (entry: %s)", entry.entry_id)

    try:
        coordinator = PCStatisticsCoordinator(hass, entry)
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

        # Listen to state changes for user and power sensors
        entry.async_on_unload(
            hass.bus.async_listen(EVENT_STATE_CHANGED, coordinator._handle_state_change)
        )

        # Reload coordinator when options change (user list/mappings edited)
        entry.async_on_unload(
            entry.add_update_listener(_async_options_updated)
        )

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


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Called when the user saves new options. Reloads the integration."""
    _LOGGER.info("Options updated, reloading PC User Statistics integration")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading PC User Statistics integration (entry: %s)", entry.entry_id)

    try:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
        if unload_ok:
            from .panel import async_unregister_panel, async_unregister_cards_resource
            async_unregister_panel(hass)
            await async_unregister_cards_resource(hass)
            hass.data[DOMAIN].pop(entry.entry_id)
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

        # Load user configuration from options, fall back to defaults
        self.user_map: dict[str, str] = config_entry.options.get(
            CONF_USER_MAPPINGS, dict(DEFAULT_USER_MAP)
        )
        self.tracked_users: list[str] = config_entry.options.get(
            CONF_TRACKED_USERS, list(DEFAULT_USERS)
        )
        _LOGGER.info(
            "User configuration loaded — tracked: %s, mappings: %s",
            self.tracked_users, self.user_map
        )

        # Current session tracking
        self.current_user: str | None = None
        self.acc_time: float = 0.0
        self.acc_energy: float = 0.0
        self.acc_cost: float = 0.0

        # Monthly tracking per user
        self.monthly: dict[str, dict[str, float]] = {
            user: {"time": 0.0, "energy": 0.0, "cost": 0.0}
            for user in self.tracked_users
        }

        # Timing and state tracking
        self.last_time: float = time.time()
        self.last_power: float = 0.0
        self.last_month: int = datetime.utcnow().month
        self.last_write_time: float = time.time()

        # InfluxDB write buffer for failed writes
        self.failed_writes: list[dict] = []

        hass.async_create_task(self._async_load_monthly_data())

        _LOGGER.debug("PCStatisticsCoordinator initialized (entry: %s)", config_entry.entry_id)

    async def _async_load_monthly_data(self) -> None:
        """Query InfluxDB for initial monthly sums asynchronously."""
        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'

        query = (
            f'SELECT SUM("time_delta") AS "time", '
            f'SUM("energy_delta") AS "energy", '
            f'SUM("cost_delta") AS "cost" '
            f'FROM {MEASUREMENT} '
            f'WHERE time >= \'{month_start}\' '
            f'GROUP BY "user"'
        )

        try:
            async with aiohttp.ClientSession() as session:
                query_params = urllib.parse.urlencode({
                    "q": query,
                    "db": self.config["database"]
                })
                auth = aiohttp.BasicAuth(
                    self.config["username"],
                    self.config["password"]
                )

                async with session.get(
                    f"http://{self.config['host']}:{self.config['port']}/query?{query_params}",
                    auth=auth,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status != 200:
                        _LOGGER.error("InfluxDB query failed: HTTP %s", response.status)
                        return

                    data = await response.json()

                    field_mappings = {"time": 1, "energy": 2, "cost": 3}
                    parsed_data = parse_influxdb_response(data, field_mappings)

                    for user, values in parsed_data.items():
                        if user in self.monthly:
                            self.monthly[user].update(values)

                    _LOGGER.info("Loaded monthly data: %s", self.monthly)

        except aiohttp.ClientError as err:
            _LOGGER.error("Failed to query monthly data from InfluxDB: %s", err)
        except Exception as err:
            _LOGGER.exception("Unexpected error loading monthly data: %s", err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data (called by coordinator at regular intervals)."""
        now = time.time()

        current_month = datetime.utcnow().month
        if current_month != self.last_month:
            _LOGGER.info("Month changed, reloading monthly data")
            await self._async_load_monthly_data()
            self.last_month = current_month

        if self.failed_writes:
            await self._retry_failed_writes()

        await self._calculate_deltas(now, force_write=True)

        # Evaluate notification rules
        try:
            nm = self.hass.data.get(DOMAIN, {}).get("notification_manager")
            if nm:
                await nm.async_evaluate(self)
        except Exception as err:
            _LOGGER.warning("Notification evaluation error: %s", err)

        return self._get_data()

    @callback
    def _handle_state_change(self, event) -> None:
        """Handle state changes for user or power sensors (sync callback)."""
        entity_id = event.data.get("entity_id")
        if entity_id not in [self.config_entry.data.get('user_entity', USER_ENTITY), self.config_entry.data.get('watt_entity', WATT_ENTITY)]:
            return
        self.hass.async_create_task(self._async_handle_state_change(event))

    async def _async_handle_state_change(self, event) -> None:
        """Async handler for state changes."""
        entity_id = event.data.get("entity_id")
        now = time.time()

        if entity_id == self.config_entry.data.get('user_entity', USER_ENTITY):
            await self._handle_user_change(event, now)
        elif entity_id == self.config_entry.data.get('watt_entity', WATT_ENTITY) and self.current_user:
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

        # Use options-based user_map instead of hardcoded constant
        new_user = self.user_map.get(user_key)

        if new_user != self.current_user:
            _LOGGER.info("User changed from %s to %s", self.current_user, new_user)

            if self.current_user:
                await self._calculate_deltas(now, force_write=True)

            self.current_user = new_user
            if new_user:
                self.acc_time = 0.0
                self.acc_energy = 0.0
                self.acc_cost = 0.0
                self.last_power = self._get_power()

            self.last_write_time = now

    async def _handle_power_change(self, now: float) -> None:
        """Handle power sensor state change."""
        await self._calculate_deltas(now)

    async def _calculate_deltas(self, now: float, force_write: bool = False) -> None:
        """Calculate and accumulate deltas, write to InfluxDB if applicable."""
        if not self.current_user:
            return

        delta_time = now - self.last_time
        if delta_time <= 0:
            _LOGGER.debug("Non-positive delta_time: %s, skipping calculation", delta_time)
            return

        current_power = self._get_power()
        avg_power = (current_power + self.last_power) / 2
        energy_delta = avg_power * delta_time / 3600000  # W → kWh

        price = self._get_price()
        cost_delta = energy_delta * price

        self.acc_time += delta_time
        self.acc_energy += energy_delta
        self.acc_cost += cost_delta

        if self.current_user in self.monthly:
            self.monthly[self.current_user]["time"] += delta_time
            self.monthly[self.current_user]["energy"] += energy_delta
            self.monthly[self.current_user]["cost"] += cost_delta

        time_since_write = now - self.last_write_time
        if force_write or time_since_write >= WRITE_THRESHOLD:
            await self._async_write_to_influx(current_power, delta_time, energy_delta, cost_delta)
            self.last_write_time = now

        self.last_power = current_power

    def _get_power(self) -> float:
        """Get net power (PC power minus meter power)."""
        watt_state = self.hass.states.get(self.config_entry.data.get('watt_entity', WATT_ENTITY))
        device_power_state = self.hass.states.get(self.config_entry.data.get('device_power_entity', DEVICE_POWER_ENTITY))

        watt = safe_float_from_state(watt_state, default=0.0, min_value=0.0)
        device_power = safe_float_from_state(device_power_state, default=0.0, min_value=0.0)

        return max(watt - device_power, 0.0)

    def _get_price(self) -> float:
        """Get current energy price."""
        price_state = self.hass.states.get(self.config_entry.data.get('price_entity', PRICE_ENTITY))
        return safe_float_from_state(price_state, default=0.0, min_value=0.0)

    async def _async_write_to_influx(
        self,
        power: float,
        time_delta: float,
        energy_delta: float,
        cost_delta: float
    ) -> None:
        """Write point to InfluxDB asynchronously. Buffers on failure."""
        timestamp_ns = int(datetime.utcnow().timestamp() * 1_000_000_000)
        point = (
            f'{MEASUREMENT},user={self.current_user} '
            f'power={power},time_delta={time_delta},'
            f'energy_delta={energy_delta},cost_delta={cost_delta} '
            f'{timestamp_ns}'
        )

        success = await self._write_point_to_influx(point)
        if not success:
            self._buffer_failed_write({"point": point, "timestamp": timestamp_ns, "attempts": 1})

    async def _write_point_to_influx(self, point: str) -> bool:
        """Attempt a single write to InfluxDB. Returns True on success."""
        try:
            async with aiohttp.ClientSession() as session:
                auth = aiohttp.BasicAuth(
                    self.config["username"],
                    self.config["password"]
                )
                async with session.post(
                    f"http://{self.config['host']}:{self.config['port']}/write?db={self.config['database']}",
                    data=point,
                    auth=auth,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status != 204:
                        _LOGGER.warning("Failed to write to InfluxDB: HTTP %s", response.status)
                        return False
                    _LOGGER.debug("Wrote data to InfluxDB: %s", point)
                    return True
        except aiohttp.ClientError as err:
            _LOGGER.warning("Failed to write to InfluxDB: %s", err)
            return False
        except Exception as err:
            _LOGGER.exception("Unexpected error writing to InfluxDB: %s", err)
            return False

    def _buffer_failed_write(self, write_data: dict) -> None:
        """Add a failed write to the buffer. Drops oldest if buffer is full."""
        if len(self.failed_writes) >= MAX_BUFFERED_WRITES:
            dropped = self.failed_writes.pop(0)
            _LOGGER.warning(
                "Write buffer full (%d/%d), dropped oldest point (ts=%s)",
                MAX_BUFFERED_WRITES, MAX_BUFFERED_WRITES, dropped.get("timestamp")
            )
        self.failed_writes.append(write_data)
        _LOGGER.info(
            "Buffered failed write (buffer size: %d/%d)",
            len(self.failed_writes), MAX_BUFFERED_WRITES
        )

    async def _retry_failed_writes(self) -> None:
        """Retry buffered failed writes. Drops points that exceed max attempts."""
        _LOGGER.info("Retrying %d buffered write(s)", len(self.failed_writes))
        still_failing: list[dict] = []

        for write_data in self.failed_writes:
            if write_data["attempts"] >= MAX_RETRY_ATTEMPTS:
                _LOGGER.error(
                    "Max retry attempts (%d) reached, dropping buffered point (ts=%s)",
                    MAX_RETRY_ATTEMPTS, write_data.get("timestamp")
                )
                continue

            write_data["attempts"] += 1
            success = await self._write_point_to_influx(write_data["point"])

            if success:
                _LOGGER.info(
                    "Successfully retried buffered write (attempt %d/%d)",
                    write_data["attempts"], MAX_RETRY_ATTEMPTS
                )
            else:
                _LOGGER.debug(
                    "Retry failed for buffered point (attempt %d/%d), will retry later",
                    write_data["attempts"], MAX_RETRY_ATTEMPTS
                )
                still_failing.append(write_data)

        self.failed_writes = still_failing

    def _get_data(self) -> dict[str, Any]:
        """Return current data snapshot."""
        return {
            "current_user": self.current_user,
            "acc_time": self.acc_time,
            "acc_energy": self.acc_energy,
            "acc_cost": self.acc_cost,
            "monthly": self.monthly,
        }
