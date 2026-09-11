# File Name: helpers.py
# Version: 2.7.0
# Description: Helper functions for parsing, validation, and formatting in the PC User Statistics integration.
# Last Updated: September 10, 2026
#
# Changes in 2.7.0:
#   Removed validate_influxdb_config() and parse_influxdb_response() —
#   InfluxDB/VictoriaMetrics dependency removed in v2.17.0.

import logging
from typing import Optional
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import State

_LOGGER = logging.getLogger(__name__)


def format_time(seconds: float) -> str:
    """
    Format time in seconds as human-readable string.
    
    Args:
        seconds: Time duration in seconds
        
    Returns:
        Formatted string like "5 timer 30 minutter" or "0 timer 0 minutter"
    """
    if seconds < 0:
        _LOGGER.warning("Negative time value received: %s, using 0", seconds)
        seconds = 0
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours} timer {minutes} minutter"


def safe_float_from_state(state: Optional[State], default: float = 0.0, min_value: Optional[float] = None, max_value: Optional[float] = None) -> float:
    """
    Safely extract a float value from a Home Assistant state object.
    
    Args:
        state: Home Assistant state object
        default: Default value if parsing fails
        min_value: Minimum allowed value (if set, values below are clamped)
        max_value: Maximum allowed value (if set, values above are clamped)
        
    Returns:
        Parsed float value or default
    """
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return default
    
    try:
        value = float(state.state)
        
        # Apply bounds if specified
        if min_value is not None and value < min_value:
            _LOGGER.debug("Value %s below minimum %s, clamping", value, min_value)
            value = min_value
        if max_value is not None and value > max_value:
            _LOGGER.debug("Value %s above maximum %s, clamping", value, max_value)
            value = max_value
            
        return value
    except (ValueError, TypeError) as err:
        _LOGGER.debug("Failed to parse state '%s' as float: %s, using default %s", state.state, err, default)
        return default


# v2.17.0: validate_influxdb_config() and parse_influxdb_response() removed —
# InfluxDB/VictoriaMetrics is gone; monthly/daily/history data now comes from
# Home Assistant's own recorder long-term statistics (see __init__.py
# _async_sum_period_from_statistics / websocket.py _query_history).