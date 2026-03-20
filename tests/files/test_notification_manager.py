# File Name: test_notification_manager.py
# Description: Tests for notification_manager.py — _fmt_time, _fmt_cost,
#              and NotificationManager rule evaluation logic.

import pytest
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from custom_components.pc_user_statistics.notification_manager import (
    _fmt_time,
    _fmt_cost,
    NotificationManager,
)


# ── _fmt_time ──────────────────────────────────────────────────────────────

class TestFmtTime:

    def test_zero_seconds(self):
        assert _fmt_time(0) == "0 minutter"

    def test_minutes_only(self):
        assert _fmt_time(1800) == "30 minutter"

    def test_one_hour(self):
        assert _fmt_time(3600) == "1t 0m"

    def test_one_hour_thirty(self):
        assert _fmt_time(5400) == "1t 30m"

    def test_two_hours(self):
        assert _fmt_time(7200) == "2t 0m"

    def test_59_minutes(self):
        assert _fmt_time(3540) == "59 minutter"


# ── _fmt_cost ──────────────────────────────────────────────────────────────

class TestFmtCost:

    def test_zero(self):
        assert _fmt_cost(0.0) == "0,00"

    def test_round_number(self):
        assert _fmt_cost(10.0) == "10,00"

    def test_decimal(self):
        assert _fmt_cost(3.14) == "3,14"

    def test_uses_comma_not_period(self):
        result = _fmt_cost(1.5)
        assert "," in result
        assert "." not in result

    def test_rounds_to_two_decimals(self):
        assert _fmt_cost(9.999) == "10,00"


# ── NotificationManager.async_evaluate ────────────────────────────────────

def make_manager():
    hass = MagicMock()
    store = MagicMock()
    store.get_devices = MagicMock(return_value=["mobile_app_phone"])
    store.get_rules = MagicMock(return_value={})
    store.get_last_sent = MagicMock(return_value=0.0)
    store.mark_sent_in_memory = MagicMock()
    store.async_flush = AsyncMock()
    return NotificationManager(hass, store), store, hass


def make_coordinator(current_user="flemming", acc_time=0.0, acc_cost=0.0, last_power=0.0):
    coord = MagicMock()
    coord.data = {
        "current_user": current_user,
        "acc_time": acc_time,
        "acc_cost": acc_cost,
    }
    coord.last_power = last_power
    coord._idle_since = None
    return coord


class TestAsyncEvaluate:

    @pytest.mark.asyncio
    async def test_no_devices_returns_early(self):
        mgr, store, hass = make_manager()
        store.get_devices.return_value = []
        coord = make_coordinator()

        await mgr.async_evaluate(coord)
        store.get_rules.assert_not_called()

    @pytest.mark.asyncio
    async def test_disabled_rule_not_triggered(self):
        mgr, store, hass = make_manager()
        store.get_rules.return_value = {
            "rule1": {
                "enabled": False,
                "trigger_type": "session_minutes",
                "trigger_value": 1,
                "user_targets": ["flemming"],
                "title": "Test",
                "message": "Test",
                "repeat": False,
                "repeat_interval": 0,
            }
        }
        coord = make_coordinator(acc_time=3600.0)
        mgr._send_notification = AsyncMock()

        await mgr.async_evaluate(coord)
        mgr._send_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_minutes_triggers_when_exceeded(self):
        mgr, store, hass = make_manager()
        store.get_rules.return_value = {
            "rule1": {
                "enabled": True,
                "trigger_type": "session_minutes",
                "trigger_value": 30,
                "user_targets": ["flemming"],
                "title": "Pause!",
                "message": "Du har spillet i {time}",
                "repeat": False,
                "repeat_interval": 0,
            }
        }
        coord = make_coordinator(current_user="flemming", acc_time=2000.0)  # ~33 min
        mgr._maybe_send = AsyncMock()

        await mgr.async_evaluate(coord)
        mgr._maybe_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_minutes_not_triggered_below_threshold(self):
        mgr, store, hass = make_manager()
        store.get_rules.return_value = {
            "rule1": {
                "enabled": True,
                "trigger_type": "session_minutes",
                "trigger_value": 60,
                "user_targets": ["flemming"],
                "title": "Pause!",
                "message": "Du har spillet i {time}",
                "repeat": False,
                "repeat_interval": 0,
            }
        }
        coord = make_coordinator(current_user="flemming", acc_time=1800.0)  # 30 min
        mgr._maybe_send = AsyncMock()

        await mgr.async_evaluate(coord)
        mgr._maybe_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_cost_triggers_when_exceeded(self):
        mgr, store, hass = make_manager()
        store.get_rules.return_value = {
            "rule1": {
                "enabled": True,
                "trigger_type": "session_cost",
                "trigger_value": 5.0,
                "user_targets": ["flemming"],
                "title": "Pris!",
                "message": "Koster {cost} kr",
                "repeat": False,
                "repeat_interval": 0,
            }
        }
        coord = make_coordinator(current_user="flemming", acc_cost=7.5)
        mgr._maybe_send = AsyncMock()

        await mgr.async_evaluate(coord)
        mgr._maybe_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_idle_pc_triggers_when_no_user_and_power_high(self):
        mgr, store, hass = make_manager()
        store.get_rules.return_value = {
            "rule1": {
                "enabled": True,
                "trigger_type": "idle_minutes",
                "trigger_value": 30,
                "user_targets": [],
                "title": "PC er tændt!",
                "message": "Ingen er logget ind",
                "repeat": True,
                "repeat_interval": 30,
            }
        }
        coord = make_coordinator(current_user=None, last_power=100.0)
        coord._idle_since = 0.0  # has been idle
        mgr._maybe_send = AsyncMock()

        await mgr.async_evaluate(coord)
        mgr._maybe_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_idle_pc_not_triggered_when_user_active(self):
        mgr, store, hass = make_manager()
        store.get_rules.return_value = {
            "rule1": {
                "enabled": True,
                "trigger_type": "idle_minutes",
                "trigger_value": 30,
                "user_targets": [],
                "title": "PC er tændt!",
                "message": "Ingen er logget ind",
                "repeat": False,
                "repeat_interval": 0,
            }
        }
        coord = make_coordinator(current_user="flemming", last_power=100.0)
        mgr._maybe_send = AsyncMock()

        await mgr.async_evaluate(coord)
        mgr._maybe_send.assert_not_called()
