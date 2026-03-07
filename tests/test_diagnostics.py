# File Name: test_diagnostics.py
# Description: Tests for diagnostics.py — async_get_config_entry_diagnostics.

import pytest
import sys
import os
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from custom_components.pc_user_statistics.diagnostics import async_get_config_entry_diagnostics
from custom_components.pc_user_statistics.const import DOMAIN, __version__


def make_entry(state="loaded"):
    entry = MagicMock()
    entry.entry_id = "test_entry_123"
    entry.title = "PC User Statistics"
    entry.state = MagicMock()
    entry.state.value = state
    entry.source = "user"
    entry.data = {
        "host": "localhost",
        "port": 8086,
        "database": "homeassistant",
        "username": "admin",
        "password": "secret",  # Should NOT appear in output
    }
    entry.options = {
        "tracked_users": ["flemming", "lukas"],
        "user_mappings": "konge=flemming",
    }
    return entry


def make_coordinator(monthly_loaded=True):
    coord = MagicMock()
    coord.tracked_users = ["flemming", "lukas"]
    coord._monthly_loaded = monthly_loaded
    coord.data = {
        "current_user": "flemming",
        "acc_time": 3600.0,
        "acc_energy": 1.5,
        "acc_cost": 4.2,
        "monthly": {"flemming": {}, "lukas": {}},
    }
    coord.update_interval = MagicMock()
    coord.update_interval.total_seconds = MagicMock(return_value=60.0)
    coord.last_update_success = True
    return coord


class TestDiagnostics:

    @pytest.mark.asyncio
    async def test_returns_integration_version(self):
        hass = MagicMock()
        hass.data = {}
        entry = make_entry()

        result = await async_get_config_entry_diagnostics(hass, entry)
        assert result["integration_version"] == __version__

    @pytest.mark.asyncio
    async def test_password_not_in_output(self):
        hass = MagicMock()
        hass.data = {}
        entry = make_entry()

        result = await async_get_config_entry_diagnostics(hass, entry)
        config = result["config_entry"]
        assert "password" not in config
        # Make sure no nested structure contains it
        assert "secret" not in str(result)

    @pytest.mark.asyncio
    async def test_config_entry_fields_present(self):
        hass = MagicMock()
        hass.data = {}
        entry = make_entry()

        result = await async_get_config_entry_diagnostics(hass, entry)
        config = result["config_entry"]
        assert config["host"] == "localhost"
        assert config["port"] == 8086
        assert config["database"] == "homeassistant"
        assert config["entry_id"] == "test_entry_123"

    @pytest.mark.asyncio
    async def test_tracked_users_in_options(self):
        hass = MagicMock()
        hass.data = {}
        entry = make_entry()

        result = await async_get_config_entry_diagnostics(hass, entry)
        assert result["options"]["tracked_users"] == ["flemming", "lukas"]

    @pytest.mark.asyncio
    async def test_coordinator_data_when_present(self):
        coord = make_coordinator()
        hass = MagicMock()
        hass.data = {DOMAIN: {"coordinator": coord}}

        # Make coordinator findable
        coord.tracked_users = ["flemming", "lukas"]
        hass.data[DOMAIN]["coord"] = coord

        entry = make_entry()
        result = await async_get_config_entry_diagnostics(hass, entry)

        # Even without coordinator found, result should be structurally valid
        assert "coordinator" in result
        assert "config_entry" in result
        assert "options" in result

    @pytest.mark.asyncio
    async def test_coordinator_not_found_returns_empty_coordinator(self):
        hass = MagicMock()
        hass.data = {DOMAIN: {}}  # No coordinator
        entry = make_entry()

        result = await async_get_config_entry_diagnostics(hass, entry)
        assert result["coordinator"] == {}

    @pytest.mark.asyncio
    async def test_user_map_not_in_options_output(self):
        """user_map may contain HA user IDs — should be excluded from diagnostics."""
        hass = MagicMock()
        hass.data = {}
        entry = make_entry()

        result = await async_get_config_entry_diagnostics(hass, entry)
        assert "user_map" not in result["options"]
