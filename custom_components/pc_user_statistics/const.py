# File Name: const.py
# Version: 2.17.0
# Description: Constants for the PC User Statistics integration.
# Last Updated: September 10, 2026
#
# Changes in 2.17.0:
#   InfluxDB/VictoriaMetrics removed — monthly/daily totals and the history
#   graph are now sourced from Home Assistant's own long-term statistics
#   (see __init__.py _async_sum_period_from_statistics). Removed the
#   InfluxDB-only constants (MEASUREMENT, DEFAULT_DATABASE, WRITE_THRESHOLD,
#   MAX_BUFFERED_WRITES, MAX_RETRY_ATTEMPTS — the retry/backoff buffer they
#   configured no longer exists, deltas now apply every poll).
#   monthly_cost changed from state_class TOTAL to TOTAL_INCREASING to match
#   monthly_time/monthly_energy — TOTAL requires an explicit last_reset
#   attribute to reset correctly at monthly rollover (which this integration
#   never set), so its long-term "sum" statistic would have been silently
#   corrupted every month once something actually read it. TOTAL_INCREASING
#   auto-detects the drop-to-0 as a meter reset instead, same as the other two.

from typing import Final

# Integration metadata
DOMAIN: Final = "pc_user_statistics"
__version__: Final = "2.17.0"

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
CONF_FAMILY_SAFETY_MAPPINGS: Final = "family_safety_mappings"  # user_id → FS entity prefix

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

# Update interval (seconds) — how often the coordinator polls and applies
# deltas to the monthly/daily trackers. This drives the monthly_*/daily
# sensors' own state updates, which is what HA's recorder observes to build
# the long-term statistics _async_sum_period_from_statistics() reads back.
UPDATE_INTERVAL: Final = 60

# Price fallback — how often (seconds) to re-log a warning while the price
# sensor stays unavailable/unknown, so a prolonged outage doesn't spam the log
PRICE_FALLBACK_LOG_INTERVAL: Final = 300

# Local timezone used for calendar-day/month boundaries (daily reset, monthly
# rollover, statistics query windows). Using UTC for these caused month
# rollover to fire up to 2 hours late in summer (CEST = UTC+2), and would
# cause the same issue for the daily tracker if left on UTC.
LOCAL_TIMEZONE: Final = "Europe/Copenhagen"

# Sensor configuration for hub and user sensors
# Format: {sensor_key: (name_key, icon, device_class, state_class, unit, suggested_display_precision)}
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

SENSOR_CONFIGS: Final = {
    # Hub sensors (global/live status)
    "current_user":           ("current_user",           "mdi:account",        None,                       None,                        None,  None),
    "current_session_time":   ("current_session_time",   "mdi:clock-outline",  SensorDeviceClass.DURATION,  SensorStateClass.MEASUREMENT, "s",   0),
    "current_session_energy": ("current_session_energy", "mdi:lightning-bolt", SensorDeviceClass.ENERGY,    SensorStateClass.TOTAL,       "kWh", 3),
    "current_session_cost":   ("current_session_cost",   "mdi:currency-usd",   SensorDeviceClass.MONETARY,  SensorStateClass.TOTAL,       "DKK", 2),

    # User sensors (per-user monthly statistics) — all TOTAL_INCREASING so
    # HA's recorder auto-detects the monthly reset and keeps long-term
    # "sum"/"change" statistics correct across it. These are also the
    # entities _async_sum_period_from_statistics() reads back from for both
    # the monthly and daily totals, and for the history graph.
    "monthly_time":   ("monthly_time",   "mdi:clock-outline",  SensorDeviceClass.DURATION, SensorStateClass.TOTAL_INCREASING, "s",   0),
    "monthly_energy": ("monthly_energy", "mdi:lightning-bolt", SensorDeviceClass.ENERGY,   SensorStateClass.TOTAL_INCREASING, "kWh", 3),
    "monthly_cost":   ("monthly_cost",   "mdi:currency-usd",   SensorDeviceClass.MONETARY, SensorStateClass.TOTAL_INCREASING, "DKK", 2),
}
