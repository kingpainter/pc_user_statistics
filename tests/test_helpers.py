# File Name: test_helpers.py
# Description: Unit tests for helpers.py — format_time, safe_float_from_state,
#              validate_influxdb_config, parse_influxdb_response.

import pytest
import sys
import os
from unittest.mock import MagicMock

# Allow importing from custom_components without a full HA install
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from custom_components.pc_user_statistics.helpers import (
    format_time,
    safe_float_from_state,
    validate_influxdb_config,
    parse_influxdb_response,
)

# We need HA constants — mock them if HA not installed
try:
    from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
except ImportError:
    STATE_UNAVAILABLE = "unavailable"
    STATE_UNKNOWN = "unknown"


# ── format_time ────────────────────────────────────────────────────────────

class TestFormatTime:

    def test_zero_seconds(self):
        assert format_time(0) == "0 timer 0 minutter"

    def test_one_hour_exactly(self):
        assert format_time(3600) == "1 timer 0 minutter"

    def test_one_hour_thirty_minutes(self):
        assert format_time(5400) == "1 timer 30 minutter"

    def test_only_minutes(self):
        assert format_time(1800) == "0 timer 30 minutter"

    def test_multiple_hours(self):
        assert format_time(7200) == "2 timer 0 minutter"

    def test_large_value(self):
        assert format_time(86400) == "24 timer 0 minutter"

    def test_fractional_seconds_truncated(self):
        # 90.9 seconds = 0 hours, 1 minute (truncated)
        assert format_time(90.9) == "0 timer 1 minutter"

    def test_negative_seconds_clamped_to_zero(self):
        # Negative values should be clamped to 0
        assert format_time(-100) == "0 timer 0 minutter"

    def test_59_minutes(self):
        assert format_time(3540) == "0 timer 59 minutter"

    def test_exactly_5_hours(self):
        assert format_time(18000) == "5 timer 0 minutter"


# ── safe_float_from_state ──────────────────────────────────────────────────

def make_state(value: str) -> MagicMock:
    s = MagicMock()
    s.state = value
    return s


class TestSafeFloatFromState:

    def test_none_state_returns_default(self):
        assert safe_float_from_state(None) == 0.0

    def test_none_state_custom_default(self):
        assert safe_float_from_state(None, default=99.9) == 99.9

    def test_unavailable_returns_default(self):
        s = make_state(STATE_UNAVAILABLE)
        assert safe_float_from_state(s) == 0.0

    def test_unknown_returns_default(self):
        s = make_state(STATE_UNKNOWN)
        assert safe_float_from_state(s) == 0.0

    def test_valid_integer_string(self):
        assert safe_float_from_state(make_state("42")) == 42.0

    def test_valid_float_string(self):
        assert safe_float_from_state(make_state("3.14")) == 3.14

    def test_negative_value(self):
        assert safe_float_from_state(make_state("-5.0")) == -5.0

    def test_invalid_string_returns_default(self):
        assert safe_float_from_state(make_state("not_a_number")) == 0.0

    def test_invalid_string_custom_default(self):
        assert safe_float_from_state(make_state("abc"), default=7.0) == 7.0

    def test_min_value_clamping(self):
        assert safe_float_from_state(make_state("-10"), min_value=0.0) == 0.0

    def test_max_value_clamping(self):
        assert safe_float_from_state(make_state("1000"), max_value=500.0) == 500.0

    def test_value_within_bounds(self):
        assert safe_float_from_state(make_state("50"), min_value=0.0, max_value=100.0) == 50.0

    def test_value_at_min_boundary(self):
        assert safe_float_from_state(make_state("0"), min_value=0.0) == 0.0

    def test_value_at_max_boundary(self):
        assert safe_float_from_state(make_state("100"), max_value=100.0) == 100.0

    def test_zero_state(self):
        assert safe_float_from_state(make_state("0")) == 0.0

    def test_empty_string_returns_default(self):
        assert safe_float_from_state(make_state("")) == 0.0


# ── validate_influxdb_config ───────────────────────────────────────────────

class TestValidateInfluxdbConfig:

    def test_valid_config(self):
        ok, err = validate_influxdb_config("localhost", 8086, "homeassistant", "admin", "secret")
        assert ok is True
        assert err is None

    def test_empty_host(self):
        ok, err = validate_influxdb_config("", 8086, "db", "user", "pass")
        assert ok is False
        assert err is not None

    def test_whitespace_only_host(self):
        ok, err = validate_influxdb_config("   ", 8086, "db", "user", "pass")
        assert ok is False

    def test_port_too_low(self):
        ok, err = validate_influxdb_config("localhost", 0, "db", "user", "pass")
        assert ok is False

    def test_port_too_high(self):
        ok, err = validate_influxdb_config("localhost", 65536, "db", "user", "pass")
        assert ok is False

    def test_port_at_min_boundary(self):
        ok, err = validate_influxdb_config("localhost", 1, "db", "user", "pass")
        assert ok is True

    def test_port_at_max_boundary(self):
        ok, err = validate_influxdb_config("localhost", 65535, "db", "user", "pass")
        assert ok is True

    def test_empty_database(self):
        ok, err = validate_influxdb_config("localhost", 8086, "", "user", "pass")
        assert ok is False

    def test_empty_username(self):
        ok, err = validate_influxdb_config("localhost", 8086, "db", "", "pass")
        assert ok is False

    def test_empty_password_still_valid(self):
        # Empty password is allowed (warned but not rejected)
        ok, err = validate_influxdb_config("localhost", 8086, "db", "user", "")
        assert ok is True

    def test_non_integer_port(self):
        ok, err = validate_influxdb_config("localhost", "8086", "db", "user", "pass")
        assert ok is False

    def test_hostname_with_dashes(self):
        ok, err = validate_influxdb_config("a0d7b954-influxdb", 8086, "homeassistant", "homeassistant", "pass")
        assert ok is True


# ── parse_influxdb_response ────────────────────────────────────────────────

class TestParseInfluxdbResponse:

    def test_valid_single_user(self):
        data = {
            "results": [{
                "series": [{
                    "tags": {"user": "flemming"},
                    "values": [[None, 3600.0, 1.5, 4.2]],
                }]
            }]
        }
        mappings = {"time": 1, "energy": 2, "cost": 3}
        result = parse_influxdb_response(data, mappings)
        assert "flemming" in result
        assert result["flemming"]["time"] == 3600.0
        assert result["flemming"]["energy"] == 1.5
        assert result["flemming"]["cost"] == 4.2

    def test_multiple_users(self):
        data = {
            "results": [{
                "series": [
                    {"tags": {"user": "flemming"}, "values": [[None, 100.0, 0.5, 1.0]]},
                    {"tags": {"user": "lukas"},    "values": [[None, 200.0, 1.0, 2.0]]},
                ]
            }]
        }
        mappings = {"time": 1, "energy": 2, "cost": 3}
        result = parse_influxdb_response(data, mappings)
        assert len(result) == 2
        assert result["lukas"]["time"] == 200.0

    def test_empty_results(self):
        result = parse_influxdb_response({"results": [{}]}, {"time": 1})
        assert result == {}

    def test_no_series(self):
        result = parse_influxdb_response({"results": [{"series": []}]}, {"time": 1})
        assert result == {}

    def test_not_a_dict(self):
        result = parse_influxdb_response("invalid", {"time": 1})
        assert result == {}

    def test_missing_results_key(self):
        result = parse_influxdb_response({}, {"time": 1})
        assert result == {}

    def test_null_value_defaults_to_zero(self):
        data = {
            "results": [{
                "series": [{
                    "tags": {"user": "flemming"},
                    "values": [[None, None, None, None]],
                }]
            }]
        }
        mappings = {"time": 1, "energy": 2, "cost": 3}
        result = parse_influxdb_response(data, mappings)
        assert result["flemming"]["time"] == 0.0
        assert result["flemming"]["energy"] == 0.0

    def test_field_index_out_of_range_defaults_to_zero(self):
        data = {
            "results": [{
                "series": [{
                    "tags": {"user": "flemming"},
                    "values": [[None, 100.0]],  # Only 2 values
                }]
            }]
        }
        mappings = {"time": 1, "energy": 5}  # index 5 doesn't exist
        result = parse_influxdb_response(data, mappings)
        assert result["flemming"]["energy"] == 0.0

    def test_missing_user_tag_skipped(self):
        data = {
            "results": [{
                "series": [{
                    "tags": {},  # No user tag
                    "values": [[None, 100.0]],
                }]
            }]
        }
        result = parse_influxdb_response(data, {"time": 1})
        assert result == {}

    def test_empty_values_list_skipped(self):
        data = {
            "results": [{
                "series": [{
                    "tags": {"user": "flemming"},
                    "values": [],
                }]
            }]
        }
        result = parse_influxdb_response(data, {"time": 1})
        assert result == {}
