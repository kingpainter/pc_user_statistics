# File Name: helpers.py
# Version: 2.0.0
# Description: Helper functions for parsing, validation, and formatting in the PC User Statistics integration.
# Last Updated: January 11, 2026

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


def validate_influxdb_config(host: str, port: int, database: str, username: str, password: str) -> tuple[bool, Optional[str]]:
    """
    Validate InfluxDB configuration parameters.
    
    Args:
        host: InfluxDB host
        port: InfluxDB port
        database: Database name
        username: Username
        password: Password
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Host validation
    if not host or not host.strip():
        return False, "Host cannot be empty"
    
    # Port validation
    if not isinstance(port, int) or port < 1 or port > 65535:
        return False, f"Port must be between 1 and 65535, got {port}"
    
    # Database validation
    if not database or not database.strip():
        return False, "Database name cannot be empty"
    
    # Username validation
    if not username or not username.strip():
        return False, "Username cannot be empty"
    
    # Password validation (can technically be empty, but warn)
    if not password:
        _LOGGER.warning("Empty password provided for InfluxDB")
    
    return True, None


def parse_influxdb_response(data: dict, field_mappings: dict[str, int]) -> dict[str, dict[str, float]]:
    """
    Parse InfluxDB query response and extract values.
    
    Args:
        data: Raw InfluxDB JSON response
        field_mappings: Dict mapping field names to their index in values array
                       e.g., {"time": 1, "energy": 2, "cost": 3}
    
    Returns:
        Dict mapping user to their field values
        e.g., {"flemming": {"time": 123.4, "energy": 5.6, "cost": 7.8}}
    """
    result = {}
    
    # Validate response structure
    if not isinstance(data, dict):
        _LOGGER.error("Invalid InfluxDB response: not a dict")
        return result
    
    results = data.get("results")
    if not results or not isinstance(results, list) or len(results) == 0:
        _LOGGER.debug("No results in InfluxDB response")
        return result
    
    series = results[0].get("series")
    if not series or not isinstance(series, list):
        _LOGGER.debug("No series in InfluxDB response")
        return result
    
    # Extract data per user
    for point_set in series:
        if not isinstance(point_set, dict):
            continue
            
        tags = point_set.get("tags", {})
        user = tags.get("user")
        
        if not user:
            continue
        
        values = point_set.get("values", [[]])
        if not values or not isinstance(values, list) or len(values) == 0:
            continue
        
        first_value = values[0]
        if not isinstance(first_value, list):
            continue
        
        # Extract fields based on mapping
        user_data = {}
        for field_name, field_index in field_mappings.items():
            try:
                if len(first_value) > field_index:
                    user_data[field_name] = first_value[field_index] or 0.0
                else:
                    user_data[field_name] = 0.0
            except (IndexError, TypeError) as err:
                _LOGGER.debug("Failed to extract field %s at index %s: %s", field_name, field_index, err)
                user_data[field_name] = 0.0
        
        result[user] = user_data
    
    return result