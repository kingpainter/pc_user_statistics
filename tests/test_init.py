# File Name: test_init.py
# Description: Unit tests for __init__.py — _normalize_user_map, write buffer,
#              repair issues, and coordinator data snapshot logic.

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# ── _normalize_user_map ────────────────────────────────────────────────────

# Import just the function — avoids needing full HA at module level
def get_normalize():
    from custom_components.pc_user_statistics.__init__ import _normalize_user_map
    return _normalize_user_map


class TestNormalizeUserMap:

    def test_plain_strings_passthrough(self):
        fn = get_normalize()
        raw = {"konge": "flemming", "lukas": "lukas"}
        result = fn(raw)
        assert result == {"konge": "flemming", "lukas": "lukas"}

    def test_dict_values_extracted(self):
        fn = get_normalize()
        raw = {
            "konge": {"user_id": "flemming", "ha_user": "abc123"},
            "lukas": {"user_id": "lukas", "ha_user": "def456"},
        }
        result = fn(raw)
        assert result == {"konge": "flemming", "lukas": "lukas"}

    def test_dict_without_user_id_skipped(self):
        fn = get_normalize()
        raw = {"konge": {"ha_user": "abc123"}}  # no user_id
        result = fn(raw)
        assert "konge" not in result

    def test_values_lowercased(self):
        fn = get_normalize()
        raw = {"KONGE": "Flemming"}
        result = fn(raw)
        assert result["KONGE"] == "flemming"

    def test_dict_user_id_lowercased(self):
        fn = get_normalize()
        raw = {"KONGE": {"user_id": "FLEMMING", "ha_user": "abc"}}
        result = fn(raw)
        assert result["KONGE"] == "flemming"

    def test_empty_string_value_skipped(self):
        fn = get_normalize()
        raw = {"konge": ""}
        result = fn(raw)
        assert "konge" not in result

    def test_integer_value_skipped(self):
        fn = get_normalize()
        raw = {"konge": 123}
        result = fn(raw)
        assert "konge" not in result

    def test_none_value_skipped(self):
        fn = get_normalize()
        raw = {"konge": None}
        result = fn(raw)
        assert "konge" not in result

    def test_empty_dict_returns_empty(self):
        fn = get_normalize()
        assert fn({}) == {}

    def test_mixed_plain_and_dict(self):
        fn = get_normalize()
        raw = {
            "konge": "flemming",
            "lukas": {"user_id": "lukas", "ha_user": "xyz"},
        }
        result = fn(raw)
        assert result == {"konge": "flemming", "lukas": "lukas"}


# ── Write buffer ───────────────────────────────────────────────────────────

class TestWriteBuffer:
    """Tests for _buffer_failed_write and _retry_failed_writes."""

    def _make_coordinator(self):
        """Build a minimal coordinator-like object with just the buffer methods."""
        # Import coordinator class
        from custom_components.pc_user_statistics.__init__ import PCStatisticsCoordinator
        from custom_components.pc_user_statistics.const import MAX_BUFFERED_WRITES, MAX_RETRY_ATTEMPTS

        hass = MagicMock()
        hass.data = {}
        hass.async_create_task = MagicMock()

        entry = MagicMock()
        entry.entry_id = "test"
        entry.data = {
            "host": "localhost", "port": 8086,
            "database": "homeassistant", "username": "admin", "password": "secret",
        }
        entry.options = {"tracked_users": ["flemming"], "user_mappings": ""}

        with patch.object(PCStatisticsCoordinator, "__init__", lambda self, h, e: None):
            coord = PCStatisticsCoordinator.__new__(PCStatisticsCoordinator)
            coord.hass = hass
            coord.failed_writes = []
            coord._unloaded = False
            coord._consecutive_write_failures = 0
            coord._REPAIR_THRESHOLD = 5
            coord._LOGGER = MagicMock()
        return coord

    def test_buffer_adds_write(self):
        from custom_components.pc_user_statistics.__init__ import PCStatisticsCoordinator
        coord = self._make_coordinator()
        coord._buffer_failed_write({"point": "test", "timestamp": 1000, "attempts": 1})
        assert len(coord.failed_writes) == 1

    def test_buffer_fifo_drops_oldest_when_full(self):
        from custom_components.pc_user_statistics.const import MAX_BUFFERED_WRITES
        coord = self._make_coordinator()
        # Fill buffer to max
        for i in range(MAX_BUFFERED_WRITES):
            coord.failed_writes.append({"point": f"p{i}", "timestamp": i, "attempts": 1})
        # Adding one more should drop the oldest
        coord._buffer_failed_write({"point": "newest", "timestamp": 9999, "attempts": 1})
        assert len(coord.failed_writes) == MAX_BUFFERED_WRITES
        assert coord.failed_writes[-1]["point"] == "newest"
        assert coord.failed_writes[0]["point"] == "p1"  # p0 was dropped

    @pytest.mark.asyncio
    async def test_retry_succeeds_clears_buffer(self):
        coord = self._make_coordinator()
        coord.failed_writes = [{"point": "p1", "timestamp": 1, "attempts": 1}]
        coord._write_point_to_influx = AsyncMock(return_value=True)
        coord._clear_repair_issue = MagicMock()
        coord._consecutive_write_failures = 0

        await coord._retry_failed_writes()
        assert coord.failed_writes == []

    @pytest.mark.asyncio
    async def test_retry_failure_keeps_in_buffer(self):
        coord = self._make_coordinator()
        coord.failed_writes = [{"point": "p1", "timestamp": 1, "attempts": 1}]
        coord._write_point_to_influx = AsyncMock(return_value=False)

        await coord._retry_failed_writes()
        assert len(coord.failed_writes) == 1
        assert coord.failed_writes[0]["attempts"] == 2

    @pytest.mark.asyncio
    async def test_retry_drops_after_max_attempts(self):
        from custom_components.pc_user_statistics.const import MAX_RETRY_ATTEMPTS
        coord = self._make_coordinator()
        coord.failed_writes = [{"point": "p1", "timestamp": 1, "attempts": MAX_RETRY_ATTEMPTS}]
        coord._write_point_to_influx = AsyncMock(return_value=False)

        await coord._retry_failed_writes()
        assert coord.failed_writes == []  # Dropped


# ── Repair issues ──────────────────────────────────────────────────────────

class TestRepairIssues:

    def _make_coord_with_hass(self):
        hass = MagicMock()
        hass.data = {}
        hass.async_create_task = MagicMock()

        coord = MagicMock()
        coord.hass = hass
        coord._consecutive_write_failures = 0
        coord._REPAIR_THRESHOLD = 5

        # Bind real methods
        from custom_components.pc_user_statistics.__init__ import PCStatisticsCoordinator
        coord._maybe_raise_repair_issue = PCStatisticsCoordinator._maybe_raise_repair_issue.__get__(coord)
        coord._clear_repair_issue = PCStatisticsCoordinator._clear_repair_issue.__get__(coord)
        return coord

    def test_repair_issue_raised_at_threshold(self):
        coord = self._make_coord_with_hass()
        coord._consecutive_write_failures = 5

        with patch("custom_components.pc_user_statistics.__init__.ir") as mock_ir:
            coord._maybe_raise_repair_issue()
            mock_ir.async_create_issue.assert_called_once()
            args = mock_ir.async_create_issue.call_args
            assert args[0][2] == "influxdb_unreachable"

    def test_repair_issue_not_raised_below_threshold(self):
        coord = self._make_coord_with_hass()
        coord._consecutive_write_failures = 3

        with patch("custom_components.pc_user_statistics.__init__.ir") as mock_ir:
            coord._maybe_raise_repair_issue()
            mock_ir.async_create_issue.assert_not_called()

    def test_clear_repair_issue_called_when_above_threshold(self):
        coord = self._make_coord_with_hass()
        coord._consecutive_write_failures = 5

        with patch("custom_components.pc_user_statistics.__init__.ir") as mock_ir:
            coord._clear_repair_issue()
            mock_ir.async_delete_issue.assert_called_once_with(
                coord.hass, "pc_user_statistics", "influxdb_unreachable"
            )

    def test_clear_repair_issue_not_called_below_threshold(self):
        coord = self._make_coord_with_hass()
        coord._consecutive_write_failures = 2

        with patch("custom_components.pc_user_statistics.__init__.ir") as mock_ir:
            coord._clear_repair_issue()
            mock_ir.async_delete_issue.assert_not_called()


# ── _get_data snapshot ─────────────────────────────────────────────────────

class TestGetData:

    def _make_coord(self, monthly_loaded=True, current_user="flemming",
                    acc_time=100.0, acc_energy=0.5, acc_cost=1.2,
                    monthly=None, pending=None):
        coord = MagicMock()
        coord._monthly_loaded = monthly_loaded
        coord.current_user = current_user
        coord.acc_time = acc_time
        coord.acc_energy = acc_energy
        coord.acc_cost = acc_cost
        coord.monthly = monthly or {"flemming": {"time": 3600.0, "energy": 1.0, "cost": 3.0}}
        coord._pending = pending or {}

        from custom_components.pc_user_statistics.__init__ import PCStatisticsCoordinator
        coord._get_data = PCStatisticsCoordinator._get_data.__get__(coord)
        return coord

    def test_returns_current_user(self):
        coord = self._make_coord(current_user="lukas")
        data = coord._get_data()
        assert data["current_user"] == "lukas"

    def test_returns_acc_values(self):
        coord = self._make_coord(acc_time=500.0, acc_energy=0.8, acc_cost=2.5)
        data = coord._get_data()
        assert data["acc_time"] == 500.0
        assert data["acc_energy"] == 0.8
        assert data["acc_cost"] == 2.5

    def test_monthly_loaded_returns_monthly(self):
        monthly = {"flemming": {"time": 3600.0, "energy": 1.0, "cost": 3.0}}
        coord = self._make_coord(monthly_loaded=True, monthly=monthly)
        data = coord._get_data()
        assert data["monthly"]["flemming"]["time"] == 3600.0

    def test_monthly_not_loaded_merges_pending(self):
        monthly = {"flemming": {"time": 0.0, "energy": 0.0, "cost": 0.0}}
        pending = {"flemming": {"time": 60.0, "energy": 0.1, "cost": 0.3}}
        coord = self._make_coord(monthly_loaded=False, monthly=monthly, pending=pending)
        data = coord._get_data()
        # When not loaded, pending is merged in
        assert data["monthly"]["flemming"]["time"] == 60.0
