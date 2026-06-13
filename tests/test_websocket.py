# File Name: test_websocket.py
# Description: Tests for websocket.py — helper functions and ws_get_stats response structure.

import pytest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from custom_components.pc_user_statistics.websocket import (
    _get_coordinator,
    _get_store,
    _get_notification_manager,
    ws_get_stats,
    ws_get_system,
    ws_get_notifications,
    ws_get_devices,
    ws_add_manual_entry,
)
from custom_components.pc_user_statistics.const import DOMAIN
from unittest.mock import AsyncMock


# ── _get_coordinator ───────────────────────────────────────────────────────

class TestGetCoordinator:

    def test_returns_coordinator_from_runtime_data(self):
        coord = MagicMock()
        entry = MagicMock()
        entry.runtime_data = coord
        hass = MagicMock()
        hass.config_entries.async_entries.return_value = [entry]

        result = _get_coordinator(hass)

        assert result is coord
        hass.config_entries.async_entries.assert_called_once_with(DOMAIN)

    def test_returns_none_when_no_entries(self):
        hass = MagicMock()
        hass.config_entries.async_entries.return_value = []
        result = _get_coordinator(hass)
        assert result is None

    def test_returns_none_when_runtime_data_is_none(self):
        entry = MagicMock()
        entry.runtime_data = None
        hass = MagicMock()
        hass.config_entries.async_entries.return_value = [entry]

        result = _get_coordinator(hass)
        assert result is None

    def test_skips_entries_without_runtime_data_and_returns_next(self):
        # Entry with no runtime_data attribute at all
        entry_without_attr = object()

        coord = MagicMock()
        entry_with_data = MagicMock()
        entry_with_data.runtime_data = coord

        hass = MagicMock()
        hass.config_entries.async_entries.return_value = [entry_without_attr, entry_with_data]

        result = _get_coordinator(hass)
        assert result is coord


# ── _get_store ─────────────────────────────────────────────────────────────

class TestGetStore:

    def test_returns_store_when_present(self):
        store = MagicMock()
        hass = MagicMock()
        hass.data = {DOMAIN: {"store": store}}
        result = _get_store(hass)
        assert result is store

    def test_returns_none_when_missing(self):
        hass = MagicMock()
        hass.data = {DOMAIN: {}}
        result = _get_store(hass)
        assert result is None

    def test_returns_none_when_domain_missing(self):
        hass = MagicMock()
        hass.data = {}
        result = _get_store(hass)
        assert result is None


# ── _get_notification_manager ──────────────────────────────────────────────

class TestGetNotificationManager:

    def test_returns_manager_when_present(self):
        mgr = MagicMock()
        hass = MagicMock()
        hass.data = {DOMAIN: {"notification_manager": mgr}}
        result = _get_notification_manager(hass)
        assert result is mgr

    def test_returns_none_when_missing(self):
        hass = MagicMock()
        hass.data = {DOMAIN: {}}
        result = _get_notification_manager(hass)
        assert result is None


# ── ws_get_stats ───────────────────────────────────────────────────────────

class TestWsGetStats:

    def _make_ws_env(self, coord_data=None):
        coord = MagicMock()
        coord.tracked_users = ["flemming", "lukas"]
        coord.user_map = {"konge": "flemming"}
        coord._monthly_loaded = True
        coord.data = coord_data or {
            "current_user": "flemming",
            "acc_time": 3600.0,
            "acc_energy": 1.5,
            "acc_cost": 4.2,
            "monthly": {},
        }
        hass = MagicMock()
        hass.data = {DOMAIN: {"coord": coord}}
        entry = MagicMock()
        entry.runtime_data = coord
        hass.config_entries.async_entries.return_value = [entry]
        connection = MagicMock()
        msg = {"id": 1}
        return hass, connection, msg, coord

    def test_sends_result_with_expected_keys(self):
        hass, connection, msg, coord = self._make_ws_env()
        ws_get_stats(hass, connection, msg)
        connection.send_result.assert_called_once()
        result = connection.send_result.call_args[0][1]
        assert "current_user" in result
        assert "acc_time" in result
        assert "monthly" in result
        assert "tracked_users" in result
        assert "monthly_loaded" in result

    def test_sends_monthly_loaded_flag(self):
        hass, connection, msg, coord = self._make_ws_env()
        coord._monthly_loaded = False
        ws_get_stats(hass, connection, msg)
        result = connection.send_result.call_args[0][1]
        assert result["monthly_loaded"] is False

    def test_sends_error_when_no_coordinator(self):
        hass = MagicMock()
        hass.data = {DOMAIN: {}}
        hass.config_entries.async_entries.return_value = []
        connection = MagicMock()
        ws_get_stats(hass, connection, {"id": 1})
        connection.send_error.assert_called_once()


# ── ws_get_system ──────────────────────────────────────────────────────────

class TestWsGetSystem:

    def test_sends_result_with_version(self):
        coord = MagicMock()
        coord.tracked_users = ["flemming"]
        coord.failed_writes = []
        coord._monthly_loaded = True
        coord.last_update_success = True
        hass = MagicMock()
        hass.data = {DOMAIN: {"coord": coord}}
        entry = MagicMock()
        entry.runtime_data = coord
        hass.config_entries.async_entries.return_value = [entry]
        connection = MagicMock()

        ws_get_system(hass, connection, {"id": 1})
        connection.send_result.assert_called_once()
        result = connection.send_result.call_args[0][1]
        assert "version" in result

    def test_sends_error_when_no_coordinator(self):
        hass = MagicMock()
        hass.data = {}
        hass.config_entries.async_entries.return_value = []
        connection = MagicMock()
        ws_get_system(hass, connection, {"id": 1})
        connection.send_error.assert_called_once()


# ── ws_get_notifications ───────────────────────────────────────────────────

class TestWsGetNotifications:

    def test_sends_result_with_rules_and_devices(self):
        store = MagicMock()
        store.get_rules = MagicMock(return_value={"rule1": {"enabled": True}})
        store.get_devices = MagicMock(return_value=["mobile_app_phone"])
        store.get_available_mobile_apps = MagicMock(return_value=[])
        hass = MagicMock()
        hass.data = {DOMAIN: {"store": store}}
        connection = MagicMock()

        ws_get_notifications(hass, connection, {"id": 1})
        connection.send_result.assert_called_once()
        result = connection.send_result.call_args[0][1]
        assert "rules" in result
        assert "devices" in result

    def test_sends_error_when_no_store(self):
        hass = MagicMock()
        hass.data = {}
        connection = MagicMock()
        ws_get_notifications(hass, connection, {"id": 1})
        connection.send_error.assert_called_once()


# ── ws_get_devices ─────────────────────────────────────────────────────────

class TestWsGetDevices:

    def test_sends_devices_list(self):
        store = MagicMock()
        store.get_devices = MagicMock(return_value=["mobile_app_phone"])
        store.get_available_mobile_apps = MagicMock(return_value=[
            {"id": "mobile_app_phone", "name": "Flemming's Phone"}
        ])
        hass = MagicMock()
        hass.data = {DOMAIN: {"store": store}}
        connection = MagicMock()

        ws_get_devices(hass, connection, {"id": 1})
        connection.send_result.assert_called_once()
        result = connection.send_result.call_args[0][1]
        assert "devices" in result
        assert "available" in result
        assert result["devices"] == ["mobile_app_phone"]


# ── ws_add_manual_entry ────────────────────────────────────────────

class TestWsAddManualEntry:

    def _make_env(self, write_success=True):
        coord = MagicMock()
        coord.tracked_users = ["flemming", "lukas", "sebastian"]
        coord.async_add_manual_entry = AsyncMock(return_value=write_success)
        hass = MagicMock()
        entry = MagicMock()
        entry.runtime_data = coord
        hass.config_entries.async_entries.return_value = [entry]
        connection = MagicMock()
        return hass, connection, coord

    @pytest.mark.asyncio
    async def test_sends_error_when_no_coordinator(self):
        hass = MagicMock()
        hass.config_entries.async_entries.return_value = []
        connection = MagicMock()
        await ws_add_manual_entry(hass, connection, {
            "id": 1, "user": "lukas", "date": "2026-06-13", "time_minutes": 450.0,
        })
        connection.send_error.assert_called_once()
        assert connection.send_error.call_args[0][1] == "not_ready"

    @pytest.mark.asyncio
    async def test_rejects_unknown_user(self):
        hass, connection, coord = self._make_env()
        await ws_add_manual_entry(hass, connection, {
            "id": 1, "user": "ukendt", "date": "2026-06-13", "time_minutes": 450.0,
        })
        connection.send_error.assert_called_once()
        assert connection.send_error.call_args[0][1] == "invalid_input"
        coord.async_add_manual_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_non_positive_time(self):
        hass, connection, coord = self._make_env()
        await ws_add_manual_entry(hass, connection, {
            "id": 1, "user": "lukas", "date": "2026-06-13", "time_minutes": 0.0,
        })
        connection.send_error.assert_called_once()
        assert connection.send_error.call_args[0][1] == "invalid_input"
        coord.async_add_manual_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_invalid_date_format(self):
        hass, connection, coord = self._make_env()
        await ws_add_manual_entry(hass, connection, {
            "id": 1, "user": "lukas", "date": "13-06-2026", "time_minutes": 450.0,
        })
        connection.send_error.assert_called_once()
        assert connection.send_error.call_args[0][1] == "invalid_input"
        coord.async_add_manual_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_sends_result(self):
        hass, connection, coord = self._make_env(write_success=True)
        await ws_add_manual_entry(hass, connection, {
            "id": 1, "user": "lukas", "date": "2026-06-13",
            "time_minutes": 450.0, "energy_kwh": 1.2375, "cost_dkk": 1.3984,
        })
        connection.send_result.assert_called_once_with(1, {"success": True})
        coord.async_add_manual_entry.assert_called_once()
        kwargs = coord.async_add_manual_entry.call_args.kwargs
        assert kwargs["user"] == "lukas"
        assert kwargs["time_delta"] == 450.0 * 60
        assert kwargs["energy_delta"] == 1.2375
        assert kwargs["cost_delta"] == 1.3984

    @pytest.mark.asyncio
    async def test_write_failure_sends_error(self):
        hass, connection, coord = self._make_env(write_success=False)
        await ws_add_manual_entry(hass, connection, {
            "id": 1, "user": "lukas", "date": "2026-06-13", "time_minutes": 450.0,
        })
        connection.send_error.assert_called_once()
        assert connection.send_error.call_args[0][1] == "write_failed"
