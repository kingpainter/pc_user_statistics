# File Name: sensor.py
# Version: 2.5.0
# Description: Sensor entities for the PC User Statistics integration.
# Last Updated: March 3, 2026
#
# Changes in 2.5.0:
#   - Hub sensors (current_user, session_time, session_energy, session_cost) now use
#     EntityCategory.DIAGNOSTIC — they are live status sensors, not primary user data.
#   - Monthly user sensors have no category (they are primary tracked data).
#   - Added `available` property — sensors report unavailable if coordinator data is None.

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SENSOR_CONFIGS,
    HUB_DEVICE_ID,
    HUB_DEVICE_NAME,
    HUB_DEVICE_MODEL,
    HUB_DEVICE_MANUFACTURER,
    __version__,
)

import logging

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PC User Statistics sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = []

    # Hub sensors (live status) — diagnostic category
    entities.append(CurrentUserSensor(coordinator, config_entry))
    entities.append(CurrentSessionTimeSensor(coordinator, config_entry))
    entities.append(CurrentSessionEnergySensor(coordinator, config_entry))
    entities.append(CurrentSessionCostSensor(coordinator, config_entry))

    # User sensors (monthly statistics) — primary data, no category
    for user in coordinator.tracked_users:
        entities.append(MonthlyTimeSensor(coordinator, config_entry, user))
        entities.append(MonthlyEnergySensor(coordinator, config_entry, user))
        entities.append(MonthlyCostSensor(coordinator, config_entry, user))

    async_add_entities(entities)
    _LOGGER.info("Added %d sensor entities for users: %s", len(entities), coordinator.tracked_users)


# ── Base classes ───────────────────────────────────────────────────────────────

class PCStatisticsHubSensor(CoordinatorEntity, SensorEntity):
    """Base class for hub sensors (live session status).

    Hub sensors are DIAGNOSTIC — they show the current live state of the PC
    session, not the primary statistical data that users care about most.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, config_entry: ConfigEntry, sensor_key: str):
        """Initialize hub sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._sensor_key = sensor_key

        config = SENSOR_CONFIGS.get(sensor_key)
        if not config:
            raise ValueError(f"Unknown sensor key: {sensor_key}")

        name_key, icon, device_class, state_class, unit, precision = config

        self._attr_unique_id              = f"{config_entry.entry_id}_hub_{sensor_key}"
        self._attr_translation_key        = name_key
        self._attr_icon                   = icon
        self._attr_device_class           = device_class
        self._attr_state_class            = state_class
        self._attr_native_unit_of_measurement = unit
        if precision is not None:
            self._attr_suggested_display_precision = precision

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{config_entry.entry_id}_{HUB_DEVICE_ID}")},
            name=HUB_DEVICE_NAME,
            manufacturer=HUB_DEVICE_MANUFACTURER,
            model=HUB_DEVICE_MODEL,
            sw_version=__version__,
        )

    @property
    def available(self) -> bool:
        """Return True if coordinator has data."""
        return self.coordinator.last_update_success and self.coordinator.data is not None


class PCStatisticsUserSensor(CoordinatorEntity, SensorEntity):
    """Base class for user sensors (monthly statistics).

    User sensors have no EntityCategory — they are primary tracked data
    that users want to see on dashboards and in statistics.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, config_entry: ConfigEntry, user: str, sensor_key: str):
        """Initialize user sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._user = user
        self._sensor_key = sensor_key

        config = SENSOR_CONFIGS.get(sensor_key)
        if not config:
            raise ValueError(f"Unknown sensor key: {sensor_key}")

        name_key, icon, device_class, state_class, unit, precision = config

        self._attr_unique_id              = f"{config_entry.entry_id}_{user}_{sensor_key}"
        self._attr_translation_key        = name_key
        self._attr_icon                   = icon
        self._attr_device_class           = device_class
        self._attr_state_class            = state_class
        self._attr_native_unit_of_measurement = unit
        if precision is not None:
            self._attr_suggested_display_precision = precision

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{config_entry.entry_id}_{user}")},
            name=f"Statistics {user.capitalize()}",
            manufacturer=HUB_DEVICE_MANUFACTURER,
            model="User Statistics",
            sw_version=__version__,
            via_device=(DOMAIN, f"{config_entry.entry_id}_{HUB_DEVICE_ID}"),
        )

    @property
    def available(self) -> bool:
        """Return True if coordinator has data and monthly data is loaded."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self.coordinator.data.get("monthly_loaded", False)
        )


# ── Hub sensors (live status) ──────────────────────────────────────────────────

class CurrentUserSensor(PCStatisticsHubSensor):
    """Sensor: currently logged-in user."""

    def __init__(self, coordinator, config_entry: ConfigEntry):
        super().__init__(coordinator, config_entry, "current_user")

    @property
    def native_value(self) -> str:
        """Return current user or 'None' when no one is logged in."""
        return self.coordinator.data.get("current_user") or "None"


class CurrentSessionTimeSensor(PCStatisticsHubSensor):
    """Sensor: current session duration in seconds."""

    def __init__(self, coordinator, config_entry: ConfigEntry):
        super().__init__(coordinator, config_entry, "current_session_time")

    @property
    def native_value(self) -> float:
        return round(self.coordinator.data.get("acc_time", 0.0), 0)


class CurrentSessionEnergySensor(PCStatisticsHubSensor):
    """Sensor: current session energy consumption in kWh."""

    def __init__(self, coordinator, config_entry: ConfigEntry):
        super().__init__(coordinator, config_entry, "current_session_energy")

    @property
    def native_value(self) -> float:
        return round(self.coordinator.data.get("acc_energy", 0.0), 3)


class CurrentSessionCostSensor(PCStatisticsHubSensor):
    """Sensor: current session electricity cost in DKK."""

    def __init__(self, coordinator, config_entry: ConfigEntry):
        super().__init__(coordinator, config_entry, "current_session_cost")

    @property
    def native_value(self) -> float:
        return round(self.coordinator.data.get("acc_cost", 0.0), 2)


# ── User sensors (monthly statistics) ─────────────────────────────────────────

class MonthlyTimeSensor(PCStatisticsUserSensor):
    """Sensor: total usage time this month in seconds."""

    def __init__(self, coordinator, config_entry: ConfigEntry, user: str):
        super().__init__(coordinator, config_entry, user, "monthly_time")

    @property
    def native_value(self) -> float:
        return round(self.coordinator.data.get("monthly", {}).get(self._user, {}).get("time", 0.0), 0)


class MonthlyEnergySensor(PCStatisticsUserSensor):
    """Sensor: total energy consumption this month in kWh."""

    def __init__(self, coordinator, config_entry: ConfigEntry, user: str):
        super().__init__(coordinator, config_entry, user, "monthly_energy")

    @property
    def native_value(self) -> float:
        return round(self.coordinator.data.get("monthly", {}).get(self._user, {}).get("energy", 0.0), 3)


class MonthlyCostSensor(PCStatisticsUserSensor):
    """Sensor: total electricity cost this month in DKK."""

    def __init__(self, coordinator, config_entry: ConfigEntry, user: str):
        super().__init__(coordinator, config_entry, user, "monthly_cost")

    @property
    def native_value(self) -> float:
        return round(self.coordinator.data.get("monthly", {}).get(self._user, {}).get("cost", 0.0), 2)
