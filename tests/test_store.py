# File Name: test_store.py
# Description: Tests for store.py — NotificationStore get/set/delete logic.

import pytest
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from custom_components.pc_user_statistics.store import NotificationStore, PREMADE_RULES


def make_store(initial_data=None):
    """Create a NotificationStore with a mocked HA Store backend."""
    hass = MagicMock()
    store = NotificationStore(hass)

    mock_ha_store = AsyncMock()
    mock_ha_store.async_load = AsyncMock(return_value=initial_data)
    mock_ha_store.async_save = AsyncMock()
    store._store = mock_ha_store

    return store


# ── PREMADE_RULES ──────────────────────────────────────────────────────────

class TestPremadeRules:

    def test_four_premade_rules_exist(self):
        assert len(PREMADE_RULES) == 4

    def test_all_rules_have_required_fields(self):
        required = {"id", "name", "trigger_type", "trigger_value", "title", "message"}
        for rule in PREMADE_RULES:
            assert required.issubset(rule.keys()), f"Rule {rule.get('id')} missing fields"

    def test_rule_ids_are_unique(self):
        ids = [r["id"] for r in PREMADE_RULES]
        assert len(ids) == len(set(ids))


# ── async_load ─────────────────────────────────────────────────────────────

class TestAsyncLoad:

    @pytest.mark.asyncio
    async def test_loads_existing_data(self):
        existing = {
            "rules": {"my_rule": {"enabled": True}},
            "devices": ["mobile_app_test"],
            "sent_history": {},
        }
        store = make_store(initial_data=existing)
        await store.async_load()
        assert store.get_devices() == ["mobile_app_test"]

    @pytest.mark.asyncio
    async def test_seeds_defaults_when_no_data(self):
        store = make_store(initial_data=None)
        await store.async_load()
        rules = store.get_rules()
        # Should have premade rules seeded
        assert len(rules) >= 4

    @pytest.mark.asyncio
    async def test_empty_data_seeds_defaults(self):
        store = make_store(initial_data={})
        await store.async_load()
        rules = store.get_rules()
        assert len(rules) >= 4


# ── get_rules / get_rule ───────────────────────────────────────────────────

class TestGetRules:

    @pytest.mark.asyncio
    async def test_get_rules_returns_dict(self):
        store = make_store(initial_data=None)
        await store.async_load()
        assert isinstance(store.get_rules(), dict)

    @pytest.mark.asyncio
    async def test_get_rule_returns_none_for_missing(self):
        store = make_store(initial_data=None)
        await store.async_load()
        assert store.get_rule("nonexistent_rule") is None

    @pytest.mark.asyncio
    async def test_get_rule_returns_existing(self):
        existing = {
            "rules": {"test_rule": {"enabled": True, "name": "Test"}},
            "devices": [],
            "sent_history": {},
        }
        store = make_store(initial_data=existing)
        await store.async_load()
        rule = store.get_rule("test_rule")
        assert rule is not None
        assert rule["name"] == "Test"


# ── async_save_rule / async_delete_rule ───────────────────────────────────

class TestSaveDeleteRule:

    @pytest.mark.asyncio
    async def test_save_rule_stores_it(self):
        store = make_store(initial_data=None)
        await store.async_load()
        await store.async_save_rule("new_rule", {"enabled": True, "name": "My Rule"})
        assert store.get_rule("new_rule") is not None

    @pytest.mark.asyncio
    async def test_delete_existing_rule_returns_true(self):
        existing = {
            "rules": {"del_me": {"enabled": True}},
            "devices": [],
            "sent_history": {},
        }
        store = make_store(initial_data=existing)
        await store.async_load()
        result = await store.async_delete_rule("del_me")
        assert result is True
        assert store.get_rule("del_me") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_rule_returns_false(self):
        store = make_store(initial_data=None)
        await store.async_load()
        result = await store.async_delete_rule("ghost_rule")
        assert result is False


# ── get_devices / async_save_devices ──────────────────────────────────────

class TestDevices:

    @pytest.mark.asyncio
    async def test_get_devices_returns_list(self):
        store = make_store(initial_data=None)
        await store.async_load()
        assert isinstance(store.get_devices(), list)

    @pytest.mark.asyncio
    async def test_save_devices_stores_them(self):
        store = make_store(initial_data=None)
        await store.async_load()
        await store.async_save_devices(["mobile_app_phone", "mobile_app_tablet"])
        assert store.get_devices() == ["mobile_app_phone", "mobile_app_tablet"]

    @pytest.mark.asyncio
    async def test_save_empty_devices(self):
        store = make_store(initial_data=None)
        await store.async_load()
        await store.async_save_devices([])
        assert store.get_devices() == []


# ── sent history ───────────────────────────────────────────────────────────

class TestSentHistory:

    @pytest.mark.asyncio
    async def test_get_last_sent_returns_zero_for_unknown(self):
        store = make_store(initial_data=None)
        await store.async_load()
        assert store.get_last_sent("unknown_rule", "flemming") == 0.0

    @pytest.mark.asyncio
    async def test_mark_sent_in_memory_updates_value(self):
        store = make_store(initial_data=None)
        await store.async_load()
        store.mark_sent_in_memory("rule1", "flemming", 1234567890.0)
        assert store.get_last_sent("rule1", "flemming") == 1234567890.0

    @pytest.mark.asyncio
    async def test_reset_session_sent_clears_user(self):
        store = make_store(initial_data=None)
        await store.async_load()
        # Mark long_session (repeat=False premade rule) as sent for flemming
        store.mark_sent_in_memory("long_session", "flemming", 9999.0)
        assert store.get_last_sent("long_session", "flemming") == 9999.0
        # reset_session_sent only clears rules with repeat=False that exist in _data["rules"]
        store.reset_session_sent("flemming")
        assert store.get_last_sent("long_session", "flemming") == 0.0

    @pytest.mark.asyncio
    async def test_reset_session_sent_only_affects_target_user(self):
        store = make_store(initial_data=None)
        await store.async_load()
        # long_session is repeat=False, pause_reminder is repeat=True
        store.mark_sent_in_memory("long_session", "flemming", 9999.0)
        store.mark_sent_in_memory("long_session", "lukas", 8888.0)
        store.reset_session_sent("flemming")
        # lukas should be unaffected
        assert store.get_last_sent("long_session", "lukas") == 8888.0


# ── Storage error resilience (v2.9.0 / v2.9.1) ────────────────────────────

class TestStorageErrorResilience:
    """Tests that storage failures are caught and logged, not propagated."""

    def make_store_with_failing_backend(self):
        """Return a fully loaded store whose backend raises on all subsequent saves."""
        hass = MagicMock()
        store = NotificationStore(hass)

        # Load phase: succeeds (returns None so defaults are seeded)
        mock_ha_store = AsyncMock()
        mock_ha_store.async_load = AsyncMock(return_value=None)
        mock_ha_store.async_save = AsyncMock()  # succeeds during load/seed
        store._store = mock_ha_store

        mock_session_store = AsyncMock()
        mock_session_store.async_load = AsyncMock(return_value={})
        mock_session_store.async_save = AsyncMock()  # succeeds during load
        store._session_store = mock_session_store

        return store

    async def _load_and_break(self, store):
        """Load the store successfully, then make the backend fail on future saves."""
        await store.async_load()
        # Now break the backend for all future saves
        store._store.async_save = AsyncMock(side_effect=Exception("disk full"))
        store._session_store.async_save = AsyncMock(side_effect=Exception("disk full"))

    @pytest.mark.asyncio
    async def test_async_flush_does_not_raise_on_storage_error(self):
        store = self.make_store_with_failing_backend()
        await self._load_and_break(store)
        await store.async_flush()

    @pytest.mark.asyncio
    async def test_async_flush_session_does_not_raise_on_storage_error(self):
        store = self.make_store_with_failing_backend()
        await self._load_and_break(store)
        store.save_session_in_memory("flemming", 100.0, 0.5, 1.2, 0.0)
        await store.async_flush_session()

    @pytest.mark.asyncio
    async def test_async_clear_session_does_not_raise_on_storage_error(self):
        store = self.make_store_with_failing_backend()
        await self._load_and_break(store)
        await store.async_clear_session()

    @pytest.mark.asyncio
    async def test_async_save_rule_does_not_raise_on_storage_error(self):
        store = self.make_store_with_failing_backend()
        await self._load_and_break(store)
        await store.async_save_rule("custom_rule", {"enabled": True, "trigger_type": "session_minutes"})

    @pytest.mark.asyncio
    async def test_async_save_devices_does_not_raise_on_storage_error(self):
        store = self.make_store_with_failing_backend()
        await self._load_and_break(store)
        await store.async_save_devices(["notify.mobile_app_test"])

    @pytest.mark.asyncio
    async def test_flush_error_logged_at_error_level(self):
        store = self.make_store_with_failing_backend()
        await self._load_and_break(store)
        with patch("custom_components.pc_user_statistics.store._LOGGER") as mock_log:
            await store.async_flush()
            mock_log.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_flush_session_error_logged_at_error_level(self):
        store = self.make_store_with_failing_backend()
        await self._load_and_break(store)
        store.save_session_in_memory("flemming", 100.0, 0.5, 1.2, 0.0)
        with patch("custom_components.pc_user_statistics.store._LOGGER") as mock_log:
            await store.async_flush_session()
            mock_log.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_in_memory_state_preserved_after_flush_error(self):
        """A failed disk write must not corrupt in-memory state."""
        store = self.make_store_with_failing_backend()
        await self._load_and_break(store)
        store.mark_sent_in_memory("pause_reminder", "flemming", 1234.0)
        await store.async_flush()
        assert store.get_last_sent("pause_reminder", "flemming") == 1234.0

    @pytest.mark.asyncio
    async def test_session_state_preserved_after_flush_session_error(self):
        store = self.make_store_with_failing_backend()
        await self._load_and_break(store)
        store.save_session_in_memory("flemming", 500.0, 1.0, 3.0, 0.0)
        await store.async_flush_session()
        snap = store.get_session()
        assert snap is not None
        assert snap["current_user"] == "flemming"
        assert snap["acc_time"] == 500.0
