# File Name: test_sensors.py
# Description: Unit tests for sensor.py — hub sensors, user sensors,
#              available property, native_value, and entity metadata.

import pytest
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from homeassistant.const import EntityCategory
except ImportError:
    EntityCategory = MagicMock()

from custom_components.pc_user_statistics.sensor import (
    CurrentUserSensor,
    CurrentSessionTimeSensor,
    CurrentSessionEnergySensor,
    CurrentSessionCostSensor,
    MonthlyTimeSensor,
    MonthlyEnergySensor,
    MonthlyCostSensor,
)


# ── Fixtures ───────────────────────────────────────────────────────────────

def make_coordinator(data=None, monthly_loaded=True):
    coord = MagicMock()
    coord.data = data or {
        "current_user": "flemming",
        "acc_time": 3600.0,
        "acc_energy": 1.5,
        "acc_cost": 4.2,
        "monthly": {
            "flemming": {"time": 7200.0, "energy": 3.0, "cost": 8.5},
            "lukas":    {"time": 1800.0, "energy": 0.5, "cost": 1.2},
        },
    }
    coord._monthly_loaded = monthly_loaded
    coord.tracked_users = ["flemming", "lukas", "sebastian"]
    coord.config_entry = MagicMock()
    coord.config_entry.entry_id = "test_entry"
    return coord


def make_entry():
    entry = MagicMock()
    entry.entry_id = "test_entry"
    return entry


# ── Hub sensor — available property ───────────────────────────────────────

class TestHubSensorAvailable:

    def test_available_when_data_present(self):
        coord = make_coordinator()
        sensor = CurrentUserSensor(coord, make_entry())
        assert sensor.available is True

    def test_unavailable_when_coordinator_data_none(self):
        coord = make_coordinator(data=None)
        coord.data = None
        sensor = CurrentUserSensor(coord, make_entry())
        assert sensor.available is False

    def test_unavailable_when_last_update_failed(self):
        coord = make_coordinator()
        coord.last_update_success = False
        sensor = CurrentUserSensor(coord, make_entry())
        assert sensor.available is False


# ── CurrentUserSensor ──────────────────────────────────────────────────────

class TestCurrentUserSensor:

    def test_native_value_returns_current_user(self):
        coord = make_coordinator()
        sensor = CurrentUserSensor(coord, make_entry())
        assert sensor.native_value == "flemming"

    def test_native_value_none_when_no_data(self):
        coord = make_coordinator()
        coord.data = None
        sensor = CurrentUserSensor(coord, make_entry())
        assert sensor.native_value is None

    def test_entity_category_is_diagnostic(self):
        coord = make_coordinator()
        sensor = CurrentUserSensor(coord, make_entry())
        assert sensor._attr_entity_category is not None


# ── CurrentSessionTimeSensor ───────────────────────────────────────────────

class TestCurrentSessionTimeSensor:

    def test_returns_acc_time(self):
        coord = make_coordinator()
        sensor = CurrentSessionTimeSensor(coord, make_entry())
        assert sensor.native_value == 3600.0

    def test_returns_zero_when_no_data(self):
        coord = make_coordinator()
        coord.data = None
        sensor = CurrentSessionTimeSensor(coord, make_entry())
        assert sensor.native_value == 0.0

    def test_unit_is_seconds(self):
        coord = make_coordinator()
        sensor = CurrentSessionTimeSensor(coord, make_entry())
        assert sensor.native_unit_of_measurement == "s"


# ── CurrentSessionEnergySensor ─────────────────────────────────────────────

class TestCurrentSessionEnergySensor:

    def test_returns_acc_energy(self):
        coord = make_coordinator()
        sensor = CurrentSessionEnergySensor(coord, make_entry())
        assert sensor.native_value == 1.5

    def test_unit_is_kwh(self):
        coord = make_coordinator()
        sensor = CurrentSessionEnergySensor(coord, make_entry())
        assert sensor.native_unit_of_measurement == "kWh"


# ── CurrentSessionCostSensor ───────────────────────────────────────────────

class TestCurrentSessionCostSensor:

    def test_returns_acc_cost(self):
        coord = make_coordinator()
        sensor = CurrentSessionCostSensor(coord, make_entry())
        assert sensor.native_value == 4.2

    def test_unit_is_dkk(self):
        coord = make_coordinator()
        sensor = CurrentSessionCostSensor(coord, make_entry())
        assert sensor.native_unit_of_measurement == "DKK"


# ── User sensor — available property ──────────────────────────────────────

class TestUserSensorAvailable:

    def test_available_when_user_in_monthly(self):
        coord = make_coordinator()
        sensor = MonthlyTimeSensor(coord, make_entry(), "flemming")
        assert sensor.available is True

    def test_unavailable_when_data_none(self):
        coord = make_coordinator()
        coord.data = None
        sensor = MonthlyTimeSensor(coord, make_entry(), "flemming")
        assert sensor.available is False

    def test_unavailable_when_last_update_failed(self):
        coord = make_coordinator()
        coord.last_update_success = False
        sensor = MonthlyTimeSensor(coord, make_entry(), "flemming")
        assert sensor.available is False


# ── MonthlyTimeSensor ──────────────────────────────────────────────────────

class TestMonthlyTimeSensor:

    def test_returns_monthly_time_for_user(self):
        coord = make_coordinator()
        sensor = MonthlyTimeSensor(coord, make_entry(), "flemming")
        assert sensor.native_value == 7200.0

    def test_returns_zero_for_unknown_user(self):
        coord = make_coordinator()
        sensor = MonthlyTimeSensor(coord, make_entry(), "unknown_user")
        assert sensor.native_value == 0.0

    def test_returns_zero_when_no_data(self):
        coord = make_coordinator()
        coord.data = None
        sensor = MonthlyTimeSensor(coord, make_entry(), "flemming")
        assert sensor.native_value == 0.0

    def test_unit_is_seconds(self):
        coord = make_coordinator()
        sensor = MonthlyTimeSensor(coord, make_entry(), "flemming")
        assert sensor.native_unit_of_measurement == "s"


# ── MonthlyEnergySensor ────────────────────────────────────────────────────

class TestMonthlyEnergySensor:

    def test_returns_monthly_energy_for_user(self):
        coord = make_coordinator()
        sensor = MonthlyEnergySensor(coord, make_entry(), "flemming")
        assert sensor.native_value == 3.0

    def test_returns_zero_for_missing_user(self):
        coord = make_coordinator()
        sensor = MonthlyEnergySensor(coord, make_entry(), "nonexistent")
        assert sensor.native_value == 0.0


# ── MonthlyCostSensor ──────────────────────────────────────────────────────

class TestMonthlyCostSensor:

    def test_returns_monthly_cost_for_user(self):
        coord = make_coordinator()
        sensor = MonthlyCostSensor(coord, make_entry(), "lukas")
        assert sensor.native_value == 1.2

    def test_returns_zero_when_no_data(self):
        coord = make_coordinator()
        coord.data = None
        sensor = MonthlyCostSensor(coord, make_entry(), "lukas")
        assert sensor.native_value == 0.0


# ── Entity metadata ────────────────────────────────────────────────────────

class TestEntityMetadata:

    def test_hub_sensor_has_entity_name_true(self):
        coord = make_coordinator()
        sensor = CurrentUserSensor(coord, make_entry())
        assert sensor.has_entity_name is True

    def test_user_sensor_has_entity_name_true(self):
        coord = make_coordinator()
        sensor = MonthlyTimeSensor(coord, make_entry(), "flemming")
        assert sensor.has_entity_name is True

    def test_hub_sensor_unique_id_contains_entry_id(self):
        coord = make_coordinator()
        sensor = CurrentUserSensor(coord, make_entry())
        assert "test_entry" in sensor.unique_id

    def test_user_sensor_unique_id_contains_user(self):
        coord = make_coordinator()
        sensor = MonthlyTimeSensor(coord, make_entry(), "flemming")
        assert "flemming" in sensor.unique_id
