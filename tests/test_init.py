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


def get_assert_string_user_map():
    from custom_components.pc_user_statistics.__init__ import _assert_string_user_map
    return _assert_string_user_map


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


# ── _assert_string_user_map (Fix 4) ────────────────────────────────────────

class TestAssertStringUserMap:

    def test_all_strings_returned_unchanged(self):
        fn = get_assert_string_user_map()
        user_map = {"konge": "flemming", "lukas": "lukas"}
        result = fn(user_map)
        assert result == user_map

    def test_empty_map_returned_unchanged(self):
        fn = get_assert_string_user_map()
        assert fn({}) == {}

    def test_non_string_value_removed_and_logged(self):
        fn = get_assert_string_user_map()
        user_map = {"konge": "flemming", "lukas": {"user_id": "lukas"}}
        with patch("custom_components.pc_user_statistics.__init__._LOGGER") as mock_logger:
            result = fn(user_map)
            mock_logger.error.assert_called_once()
        assert result == {"konge": "flemming"}
        assert "lukas" not in result

    def test_all_non_string_values_results_in_empty_map(self):
        fn = get_assert_string_user_map()
        user_map = {"konge": 123, "lukas": None}
        with patch("custom_components.pc_user_statistics.__init__._LOGGER"):
            result = fn(user_map)
        assert result == {}


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
        coord.tracked_users = ["flemming"]
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
        # monthly must have all tracked_users as keys (zeroed out at startup)
        monthly = {"flemming": {"time": 0.0, "energy": 0.0, "cost": 0.0}}
        pending = {"flemming": {"time": 60.0, "energy": 0.1, "cost": 0.3}}
        coord = self._make_coord(monthly_loaded=False, monthly=monthly, pending=pending)
        data = coord._get_data()
        # pending is merged: 0.0 + 60.0 = 60.0
        assert data["monthly"]["flemming"]["time"] == 60.0
        assert data["monthly_loaded"] is False


# ── _schedule_session_flush liveness guard (Fix 2) ─────────────────────────

class TestScheduleSessionFlushLivenessGuard:
    """Tests for the Fix 2 overdue-flush warning in _schedule_session_flush."""

    def _make_coord(self, last_flush_monotonic=0.0, current_user=None, unloaded=False):
        from custom_components.pc_user_statistics.__init__ import PCStatisticsCoordinator

        hass = MagicMock()
        hass.async_create_task = MagicMock()

        coord = MagicMock()
        coord.hass = hass
        coord._unloaded = unloaded
        coord._last_flush_monotonic = last_flush_monotonic
        coord.current_user = current_user
        coord._session_flush_cancel = None
        coord._schedule_session_flush = PCStatisticsCoordinator._schedule_session_flush.__get__(coord)
        return coord

    @patch("custom_components.pc_user_statistics.__init__.async_call_later")
    @patch("custom_components.pc_user_statistics.__init__.time")
    def test_warns_when_flush_overdue_with_active_session(self, mock_time, mock_call_later):
        mock_time.monotonic.return_value = 1000.0
        coord = self._make_coord(last_flush_monotonic=800.0, current_user="flemming")  # 200s overdue

        with patch("custom_components.pc_user_statistics.__init__._LOGGER") as mock_logger:
            coord._schedule_session_flush()
            mock_logger.warning.assert_called_once()

    @patch("custom_components.pc_user_statistics.__init__.async_call_later")
    @patch("custom_components.pc_user_statistics.__init__.time")
    def test_no_warning_when_flush_recent(self, mock_time, mock_call_later):
        mock_time.monotonic.return_value = 1000.0
        coord = self._make_coord(last_flush_monotonic=970.0, current_user="flemming")  # 30s

        with patch("custom_components.pc_user_statistics.__init__._LOGGER") as mock_logger:
            coord._schedule_session_flush()
            mock_logger.warning.assert_not_called()

    @patch("custom_components.pc_user_statistics.__init__.async_call_later")
    @patch("custom_components.pc_user_statistics.__init__.time")
    def test_no_warning_when_no_active_user(self, mock_time, mock_call_later):
        mock_time.monotonic.return_value = 1000.0
        coord = self._make_coord(last_flush_monotonic=800.0, current_user=None)  # 200s, but idle

        with patch("custom_components.pc_user_statistics.__init__._LOGGER") as mock_logger:
            coord._schedule_session_flush()
            mock_logger.warning.assert_not_called()

    @patch("custom_components.pc_user_statistics.__init__.async_call_later")
    @patch("custom_components.pc_user_statistics.__init__.time")
    def test_no_warning_on_first_run(self, mock_time, mock_call_later):
        mock_time.monotonic.return_value = 1000.0
        coord = self._make_coord(last_flush_monotonic=0.0, current_user="flemming")  # never flushed yet

        with patch("custom_components.pc_user_statistics.__init__._LOGGER") as mock_logger:
            coord._schedule_session_flush()
            mock_logger.warning.assert_not_called()

    @patch("custom_components.pc_user_statistics.__init__.async_call_later")
    def test_returns_early_when_unloaded(self, mock_call_later):
        coord = self._make_coord(unloaded=True)
        coord._schedule_session_flush()
        mock_call_later.assert_not_called()

    @patch("custom_components.pc_user_statistics.__init__.async_call_later")
    @patch("custom_components.pc_user_statistics.__init__.time")
    def test_cancels_previous_timer_before_rescheduling(self, mock_time, mock_call_later):
        mock_time.monotonic.return_value = 1000.0
        coord = self._make_coord(last_flush_monotonic=990.0, current_user="flemming")
        previous_cancel = MagicMock()
        coord._session_flush_cancel = previous_cancel

        coord._schedule_session_flush()

        previous_cancel.assert_called_once()
        mock_call_later.assert_called_once()


# ── _escape_influx_tag (v2.12.1) ──────────────────────────────────────────

def get_escape_influx_tag():
    from custom_components.pc_user_statistics.__init__ import _escape_influx_tag
    return _escape_influx_tag


class TestEscapeInfluxTag:

    def test_plain_name_unchanged(self):
        fn = get_escape_influx_tag()
        assert fn("flemming") == "flemming"

    def test_space_escaped(self):
        fn = get_escape_influx_tag()
        assert fn("john doe") == r"john\ doe"

    def test_comma_escaped(self):
        fn = get_escape_influx_tag()
        assert fn("a,b") == r"a\,b"

    def test_equals_escaped(self):
        fn = get_escape_influx_tag()
        assert fn("a=b") == r"a\=b"

    def test_multiple_specials_all_escaped(self):
        fn = get_escape_influx_tag()
        assert fn("a b,c=d") == r"a\ b\,c\=d"

    def test_empty_string_unchanged(self):
        fn = get_escape_influx_tag()
        assert fn("") == ""

    def test_normal_users_unchanged(self):
        fn = get_escape_influx_tag()
        for name in ("flemming", "lukas", "sebastian", "ADMIN", "user123"):
            assert fn(name) == name


# ── _retry_failed_writes backoff (v2.12.0 Fix 3) ───────────────────────────

class TestRetryBackoff:
    """Tests for the exponential backoff in _retry_failed_writes."""

    def _make_coordinator(self):
        from custom_components.pc_user_statistics.__init__ import PCStatisticsCoordinator
        hass = MagicMock()
        hass.data = {}
        hass.async_create_task = MagicMock()
        coord = MagicMock()
        coord.hass = hass
        coord.failed_writes = []
        coord._retry_skip_count = 0
        coord._retry_skip_remaining = 0
        coord._retry_failed_writes = PCStatisticsCoordinator._retry_failed_writes.__get__(coord)
        return coord

    @pytest.mark.asyncio
    async def test_success_resets_backoff(self):
        coord = self._make_coordinator()
        coord._retry_skip_count = 8
        coord._retry_skip_remaining = 8
        coord.failed_writes = [{"point": "p1", "timestamp": 1, "attempts": 1}]
        coord._write_point_to_influx = AsyncMock(return_value=True)
        await coord._retry_failed_writes()
        assert coord._retry_skip_count == 0
        assert coord._retry_skip_remaining == 0

    @pytest.mark.asyncio
    async def test_all_fail_sets_initial_backoff(self):
        coord = self._make_coordinator()
        coord.failed_writes = [{"point": "p1", "timestamp": 1, "attempts": 1}]
        coord._write_point_to_influx = AsyncMock(return_value=False)
        await coord._retry_failed_writes()
        assert coord._retry_skip_count == 2
        assert coord._retry_skip_remaining == 2

    @pytest.mark.asyncio
    async def test_backoff_doubles_on_repeated_failure(self):
        coord = self._make_coordinator()
        coord._retry_skip_count = 4
        coord.failed_writes = [{"point": "p1", "timestamp": 1, "attempts": 1}]
        coord._write_point_to_influx = AsyncMock(return_value=False)
        await coord._retry_failed_writes()
        assert coord._retry_skip_count == 8

    @pytest.mark.asyncio
    async def test_backoff_capped_at_32(self):
        coord = self._make_coordinator()
        coord._retry_skip_count = 32
        coord.failed_writes = [{"point": "p1", "timestamp": 1, "attempts": 1}]
        coord._write_point_to_influx = AsyncMock(return_value=False)
        await coord._retry_failed_writes()
        assert coord._retry_skip_count == 32

    @pytest.mark.asyncio
    async def test_empty_buffer_does_not_touch_backoff(self):
        coord = self._make_coordinator()
        coord._retry_skip_count = 4
        coord._retry_skip_remaining = 2
        coord.failed_writes = []
        coord._write_point_to_influx = AsyncMock()
        await coord._retry_failed_writes()
        assert coord._retry_skip_count == 4
        assert coord._retry_skip_remaining == 2


# ── asyncio.Lock concurrent guard (v2.12.1 Fix 7) ──────────────────────────

class TestUpdateLockGuard:
    """Tests for the asyncio.Lock guard in _async_update_data."""

    @pytest.mark.asyncio
    async def test_skips_poll_when_lock_held(self):
        from custom_components.pc_user_statistics.__init__ import PCStatisticsCoordinator
        import asyncio

        coord = MagicMock()
        coord._update_lock = asyncio.Lock()
        coord._get_data = MagicMock(return_value={"skipped": True})
        coord._async_update_data = PCStatisticsCoordinator._async_update_data.__get__(coord)

        # Acquire the lock to simulate an in-progress update
        await coord._update_lock.acquire()
        try:
            result = await coord._async_update_data()
        finally:
            coord._update_lock.release()

        assert result == {"skipped": True}
        coord._get_data.assert_called_once()


# ── last_power reset on logout (v2.12.1 Fix 4) ─────────────────────────────

class TestLastPowerResetOnLogout:
    """Tests that last_power is zeroed on logout to avoid stale avg_power."""

    @pytest.mark.asyncio
    async def test_last_power_zeroed_on_logout(self):
        from custom_components.pc_user_statistics.__init__ import PCStatisticsCoordinator
        import time as _time

        hass = MagicMock()
        hass.data = {"pc_user_statistics": {"store": None}}
        hass.async_create_task = MagicMock()

        coord = MagicMock()
        coord.hass = hass
        coord.current_user = "flemming"
        coord.user_map = {"kong": "flemming"}
        coord.last_power = 250.0  # stale power reading
        coord.acc_time = 100.0
        coord.acc_energy = 0.5
        coord.acc_cost = 1.2
        coord.last_time = _time.time()
        coord.last_write_time = _time.time()
        coord._idle_since = None
        coord._calculate_deltas = AsyncMock()
        coord._handle_user_change = PCStatisticsCoordinator._handle_user_change.__get__(coord)

        # Simulate logout: new_state is None
        event = MagicMock()
        event.data = {"new_state": None}
        now = _time.time()

        await coord._handle_user_change(event, now)

        assert coord.last_power == 0.0


class TestAsyncAddManualEntry:
    """Tests for coordinator.async_add_manual_entry (manual correction)."""

    def _make_coord(self, monthly_loaded=True, write_success=True):
        from custom_components.pc_user_statistics.__init__ import PCStatisticsCoordinator
        coord = MagicMock()
        coord._monthly_loaded = monthly_loaded
        coord._write_point_to_influx = AsyncMock(return_value=write_success)
        coord._async_load_monthly_data = AsyncMock()
        coord.async_add_manual_entry = PCStatisticsCoordinator.async_add_manual_entry.__get__(coord)
        return coord

    @pytest.mark.asyncio
    async def test_writes_point_tagged_manual(self):
        coord = self._make_coord(monthly_loaded=True)
        result = await coord.async_add_manual_entry(
            user="lukas", timestamp_ns=1718280000000000000,
            time_delta=27000, energy_delta=1.2375, cost_delta=1.3984,
        )
        assert result is True
        coord._write_point_to_influx.assert_called_once()
        point = coord._write_point_to_influx.call_args[0][0]
        assert "user=lukas" in point
        assert "source=manual" in point
        assert "time_delta=27000" in point
        assert "energy_delta=1.2375" in point
        assert "cost_delta=1.3984" in point

    @pytest.mark.asyncio
    async def test_reloads_monthly_when_already_loaded(self):
        coord = self._make_coord(monthly_loaded=True)
        await coord.async_add_manual_entry("lukas", 123, 60)
        coord._async_load_monthly_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_reload_monthly_when_not_loaded(self):
        coord = self._make_coord(monthly_loaded=False)
        await coord.async_add_manual_entry("lukas", 123, 60)
        coord._async_load_monthly_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_false_and_skips_reload_on_write_failure(self):
        coord = self._make_coord(monthly_loaded=True, write_success=False)
        result = await coord.async_add_manual_entry("lukas", 123, 60)
        assert result is False
        coord._async_load_monthly_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_default_energy_and_cost_are_zero(self):
        coord = self._make_coord(monthly_loaded=True)
        await coord.async_add_manual_entry("lukas", 123, 60)
        point = coord._write_point_to_influx.call_args[0][0]
        assert "energy_delta=0.0" in point
        assert "cost_delta=0.0" in point
