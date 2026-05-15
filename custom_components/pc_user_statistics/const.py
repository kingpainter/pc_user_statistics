# File Name: const.py
# Version: 2.7.2
# Description: Constants for the PC User Statistics integration.
# Last Updated: March 16, 2026

from typing import Final

# Integration metadata
DOMAIN: Final = "pc_user_statistics"
__version__: Final = "2.7.4"

# Device identifiers
HUB_DEVICE_ID: Final = "statistics_hub"
HUB_DEVICE_NAME: Final = "Statistics Hub"
HUB_DEVICE_MODEL: Final = "PC Statistics Tracker"
HUB_DEVICE_MANUFACTURER: Final = "PC User Statistics"

# Entity IDs for monitoring
USER_ENTITY: Final = "sensor.flemming_gamer_satellite_loggeduser"
WATT_ENTITY: Final = "sensor.gamer_pc_power_monitor_current_consumption"
DEVICE_POWER_ENTITY: Final = "sensor.gamer_pc_power_monitor_device_power"
PRICE_ENTITY: Final = "sensor.energi_data_service"

# Config entry keys for user configuration
CONF_USER_MAPPINGS: Final = "user_mappings"
CONF_TRACKED_USERS: Final = "tracked_users"

# Default user mappings (sensor state → user ID)
DEFAULT_USER_MAP: Final = {
    "konge": "flemming",
    "lukas": "lukas",
    "sebas": "sebastian",
}

# Default list of tracked users
DEFAULT_USERS: Final = ["flemming", "lukas", "sebastian"]

# Legacy aliases (used internally by coordinator)
USER_MAP: Final = DEFAULT_USER_MAP
USERS: Final = DEFAULT_USERS

# InfluxDB configuration
MEASUREMENT: Final = "pc_usage"
DEFAULT_DATABASE: Final = "homeassistant"

# Update intervals (seconds)
UPDATE_INTERVAL: Final = 60
WRITE_THRESHOLD: Final = 60  # Write to InfluxDB after this many seconds

# InfluxDB write buffer (for failed writes)
MAX_BUFFERED_WRITES: Final = 100  # Max points to buffer (FIFO, oldest dropped when full)
MAX_RETRY_ATTEMPTS: Final = 3     # Max retry attempts per buffered point

# Sensor configuration for hub and user sensors
# Format: {sensor_key: (name_key, icon, device_class, state_class, unit, suggested_display_precision)}
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

SENSOR_CONFIGS: Final = {
    # Hub sensors (global/live status)
    "current_user":           ("current_user",           "mdi:account",        None,                       None,                        None,  None),
    "current_session_time":   ("current_session_time",   "mdi:clock-outline",  SensorDeviceClass.DURATION,  SensorStateClass.MEASUREMENT, "s",   0),
    "current_session_energy": ("current_session_energy", "mdi:lightning-bolt", SensorDeviceClass.ENERGY,    SensorStateClass.TOTAL,       "kWh", 3),
    "current_session_cost":   ("current_session_cost",   "mdi:currency-usd",   SensorDeviceClass.MONETARY,  SensorStateClass.TOTAL,       "DKK", 2),

    # User sensors (per-user monthly statistics)
    "monthly_time":   ("monthly_time",   "mdi:clock-outline",  SensorDeviceClass.DURATION, SensorStateClass.TOTAL_INCREASING, "s",   0),
    "monthly_energy": ("monthly_energy", "mdi:lightning-bolt", SensorDeviceClass.ENERGY,   SensorStateClass.TOTAL_INCREASING, "kWh", 3),
    "monthly_cost":   ("monthly_cost",   "mdi:currency-usd",   SensorDeviceClass.MONETARY, SensorStateClass.TOTAL,            "DKK", 2),
}
