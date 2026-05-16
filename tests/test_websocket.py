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
)
from custom_components.pc_user_statistics.const import DOMAIN


# ── _get_coordinator ───────────────────────────────────────────────────────

class TestGetCoordinator:

    def test_returns_coordinator_when_present(self):
        coord = MagicMock()
        coord.tracked_users = ["flemming"]
        hass = MagicMock()
        hass.data = {DOMAIN: {"coord": coord}}
        result = _get_coordinator(hass)
        assert result is coord

    def test_returns_none_when_domain_not_in_data(self):
        hass = MagicMock()
        hass.data = {}
        result = _get_coordinator(hass)
        assert result is None

    def test_returns_none_when_no_coordinator_with_tracked_users(self):
        # MagicMock(spec=object) has no extra attributes — hasattr returns False
        plain_mock = MagicMock(spec=object)
        hass = MagicMock()
        hass.data = {DOMAIN: {"store": plain_mock}}
        result = _get_coordinator(hass)
        assert result is None

    def test_returns_none_when_domain_empty(self):
        hass = MagicMock()
        hass.data = {DOMAIN: {}}
        result = _get_coordinator(hass)
        assert result is None


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
        connection = MagicMock()

        ws_get_system(hass, connection, {"id": 1})
        connection.send_result.assert_called_once()
        result = connection.send_result.call_args[0][1]
        assert "version" in result

    def test_sends_error_when_no_coordinator(self):
        hass = MagicMock()
        hass.data = {}
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
