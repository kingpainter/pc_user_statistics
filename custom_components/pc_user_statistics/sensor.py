# File Name: sensor.py
# Version: 2.1.0
# Description: Sensor entities for the PC User Statistics integration, providing live and monthly statistics with device organization.
# Last Updated: March 1, 2026

from homeassistant.components.sensor import SensorEntity
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
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up PC User Statistics sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = []

    # Hub sensors (live status) - attached to hub device
    entities.append(CurrentUserSensor(coordinator, config_entry))
    entities.append(CurrentSessionTimeSensor(coordinator, config_entry))
    entities.append(CurrentSessionEnergySensor(coordinator, config_entry))
    entities.append(CurrentSessionCostSensor(coordinator, config_entry))

    # User sensors (monthly statistics) - attached to individual user devices
    for user in coordinator.tracked_users:
        entities.append(MonthlyTimeSensor(coordinator, config_entry, user))
        entities.append(MonthlyEnergySensor(coordinator, config_entry, user))
        entities.append(MonthlyCostSensor(coordinator, config_entry, user))

    async_add_entities(entities)
    _LOGGER.info("Added %d sensor entities", len(entities))


class PCStatisticsHubSensor(CoordinatorEntity, SensorEntity):
    """Base class for hub sensors (live status)."""
    
    _attr_has_entity_name = True

    def __init__(self, coordinator, config_entry: ConfigEntry, sensor_key: str):
        """Initialize hub sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._sensor_key = sensor_key
        
        # Get sensor config
        config = SENSOR_CONFIGS.get(sensor_key)
        if not config:
            raise ValueError(f"Unknown sensor key: {sensor_key}")
        
        name_key, icon, device_class, state_class, unit, precision = config
        
        # Entity properties
        self._attr_unique_id = f"{config_entry.entry_id}_hub_{sensor_key}"
        self._attr_translation_key = name_key
        self._attr_icon = icon
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit
        if precision is not None:
            self._attr_suggested_display_precision = precision
        
        # Device info - hub device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{config_entry.entry_id}_{HUB_DEVICE_ID}")},
            name=HUB_DEVICE_NAME,
            manufacturer=HUB_DEVICE_MANUFACTURER,
            model=HUB_DEVICE_MODEL,
            sw_version=__version__,
        )


class PCStatisticsUserSensor(CoordinatorEntity, SensorEntity):
    """Base class for user sensors (monthly statistics)."""
    
    _attr_has_entity_name = True

    def __init__(self, coordinator, config_entry: ConfigEntry, user: str, sensor_key: str):
        """Initialize user sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._user = user
        self._sensor_key = sensor_key
        
        # Get sensor config
        config = SENSOR_CONFIGS.get(sensor_key)
        if not config:
            raise ValueError(f"Unknown sensor key: {sensor_key}")
        
        name_key, icon, device_class, state_class, unit, precision = config
        
        # Entity properties
        self._attr_unique_id = f"{config_entry.entry_id}_{user}_{sensor_key}"
        self._attr_translation_key = name_key
        self._attr_icon = icon
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit
        if precision is not None:
            self._attr_suggested_display_precision = precision
        
        # Device info - user device linked to hub
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{config_entry.entry_id}_{user}")},
            name=f"Statistics {user.capitalize()}",
            manufacturer=HUB_DEVICE_MANUFACTURER,
            model="User Statistics",
            sw_version=__version__,
            via_device=(DOMAIN, f"{config_entry.entry_id}_{HUB_DEVICE_ID}"),
        )


# Hub sensors (live status)

class CurrentUserSensor(PCStatisticsHubSensor):
    """Sensor for current user."""

    def __init__(self, coordinator, config_entry: ConfigEntry):
        super().__init__(coordinator, config_entry, "current_user")

    @property
    def native_value(self) -> str:
        """Return current user."""
        return self.coordinator.data.get("current_user") or "None"


class CurrentSessionTimeSensor(PCStatisticsHubSensor):
    """Sensor for current session time."""

    def __init__(self, coordinator, config_entry: ConfigEntry):
        super().__init__(coordinator, config_entry, "current_session_time")

    @property
    def native_value(self) -> float:
        """Return current session time in seconds."""
        return round(self.coordinator.data.get("acc_time", 0.0), 0)


class CurrentSessionEnergySensor(PCStatisticsHubSensor):
    """Sensor for current session energy."""

    def __init__(self, coordinator, config_entry: ConfigEntry):
        super().__init__(coordinator, config_entry, "current_session_energy")

    @property
    def native_value(self) -> float:
        """Return current session energy in kWh."""
        return round(self.coordinator.data.get("acc_energy", 0.0), 3)


class CurrentSessionCostSensor(PCStatisticsHubSensor):
    """Sensor for current session cost."""

    def __init__(self, coordinator, config_entry: ConfigEntry):
        super().__init__(coordinator, config_entry, "current_session_cost")

    @property
    def native_value(self) -> float:
        """Return current session cost in DKK."""
        return round(self.coordinator.data.get("acc_cost", 0.0), 2)


# User sensors (monthly statistics)

class MonthlyTimeSensor(PCStatisticsUserSensor):
    """Sensor for monthly time per user."""

    def __init__(self, coordinator, config_entry: ConfigEntry, user: str):
        super().__init__(coordinator, config_entry, user, "monthly_time")

    @property
    def native_value(self) -> float:
        """Return monthly time in seconds."""
        monthly_data = self.coordinator.data.get("monthly", {})
        user_data = monthly_data.get(self._user, {})
        return round(user_data.get("time", 0.0), 0)


class MonthlyEnergySensor(PCStatisticsUserSensor):
    """Sensor for monthly energy per user."""

    def __init__(self, coordinator, config_entry: ConfigEntry, user: str):
        super().__init__(coordinator, config_entry, user, "monthly_energy")

    @property
    def native_value(self) -> float:
        """Return monthly energy in kWh."""
        monthly_data = self.coordinator.data.get("monthly", {})
        user_data = monthly_data.get(self._user, {})
        return round(user_data.get("energy", 0.0), 3)


class MonthlyCostSensor(PCStatisticsUserSensor):
    """Sensor for monthly cost per user."""

    def __init__(self, coordinator, config_entry: ConfigEntry, user: str):
        super().__init__(coordinator, config_entry, user, "monthly_cost")

    @property
    def native_value(self) -> float:
        """Return monthly cost in DKK."""
        monthly_data = self.coordinator.data.get("monthly", {})
        user_data = monthly_data.get(self._user, {})
        return round(user_data.get("cost", 0.0), 2)