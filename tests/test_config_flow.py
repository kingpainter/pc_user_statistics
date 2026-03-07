# File Name: test_config_flow.py
# Description: Tests for config_flow.py — initial setup, reconfigure, options flow,
#              and InfluxDB connection validation.

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from custom_components.pc_user_statistics.helpers import validate_influxdb_config


# ── validate_influxdb_config (also tested in test_helpers.py, but
#    duplicated here for config_flow context clarity) ────────────────────────

class TestInfluxdbConfigValidation:

    def test_valid_returns_true(self):
        ok, err = validate_influxdb_config("localhost", 8086, "homeassistant", "admin", "secret")
        assert ok is True
        assert err is None

    def test_empty_host_fails(self):
        ok, err = validate_influxdb_config("", 8086, "homeassistant", "admin", "secret")
        assert ok is False

    def test_invalid_port_fails(self):
        ok, err = validate_influxdb_config("localhost", -1, "homeassistant", "admin", "secret")
        assert ok is False

    def test_empty_database_fails(self):
        ok, err = validate_influxdb_config("localhost", 8086, "", "admin", "secret")
        assert ok is False

    def test_empty_username_fails(self):
        ok, err = validate_influxdb_config("localhost", 8086, "homeassistant", "", "secret")
        assert ok is False


# ── async_check_influxdb_connection ───────────────────────────────────────

class TestAsyncCheckInfluxdbConnection:

    @pytest.mark.asyncio
    async def test_successful_connection(self):
        from custom_components.pc_user_statistics.config_flow import async_check_influxdb_connection

        mock_hass = MagicMock()
        mock_ping_resp = MagicMock()
        mock_ping_resp.status = 204

        mock_query_resp = MagicMock()
        mock_query_resp.status = 200
        mock_query_resp.json = AsyncMock(return_value={
            "results": [{"series": [{"values": [["homeassistant"]]}]}]
        })

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_get_ping = MagicMock()
        mock_get_ping.__aenter__ = AsyncMock(return_value=mock_ping_resp)
        mock_get_ping.__aexit__ = AsyncMock(return_value=False)

        mock_get_query = MagicMock()
        mock_get_query.__aenter__ = AsyncMock(return_value=mock_query_resp)
        mock_get_query.__aexit__ = AsyncMock(return_value=False)

        mock_session.get = MagicMock(side_effect=[mock_get_ping, mock_get_query])

        with patch("aiohttp.ClientSession", return_value=mock_session):
            ok, err = await async_check_influxdb_connection(
                mock_hass, "localhost", 8086, "admin", "secret", "homeassistant"
            )
        assert ok is True
        # Function returns "" on success (not None)
        assert err == ""

    @pytest.mark.asyncio
    async def test_ping_fails_returns_cannot_connect(self):
        from custom_components.pc_user_statistics.config_flow import async_check_influxdb_connection
        import aiohttp

        mock_hass = MagicMock()
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_get = MagicMock()
        mock_get.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("connection refused"))
        mock_get.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_get)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            ok, err = await async_check_influxdb_connection(
                mock_hass, "badhost", 9999, "admin", "secret", "homeassistant"
            )
        assert ok is False
        assert err == "cannot_connect"

    @pytest.mark.asyncio
    async def test_invalid_config_returns_invalid_config(self):
        from custom_components.pc_user_statistics.config_flow import async_check_influxdb_connection

        mock_hass = MagicMock()
        ok, err = await async_check_influxdb_connection(
            mock_hass, "", 8086, "admin", "secret", "homeassistant"
        )
        assert ok is False
        assert err == "invalid_config"


# ── ConfigFlow step_user ───────────────────────────────────────────────────

class TestConfigFlowStepUser:

    @pytest.mark.asyncio
    async def test_shows_form_on_first_call(self):
        from custom_components.pc_user_statistics.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = MagicMock()
        flow.context = {}
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        flow.async_show_form = MagicMock(return_value={"type": "form"})

        result = await flow.async_step_user(None)
        flow.async_show_form.assert_called_once()
        assert result["type"] == "form"

    @pytest.mark.asyncio
    async def test_creates_entry_on_valid_input(self):
        from custom_components.pc_user_statistics.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = MagicMock()
        flow.context = {}
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

        user_input = {
            "host": "localhost", "port": 8086,
            "database": "homeassistant", "username": "admin", "password": "secret",
        }

        with patch(
            "custom_components.pc_user_statistics.config_flow.async_check_influxdb_connection",
            AsyncMock(return_value=(True, None))
        ):
            result = await flow.async_step_user(user_input)

        flow.async_create_entry.assert_called_once()
        assert result["type"] == "create_entry"

    @pytest.mark.asyncio
    async def test_shows_error_on_failed_connection(self):
        from custom_components.pc_user_statistics.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = MagicMock()
        flow.context = {}
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        flow.async_show_form = MagicMock(return_value={"type": "form"})

        user_input = {
            "host": "badhost", "port": 8086,
            "database": "homeassistant", "username": "admin", "password": "wrong",
        }

        with patch(
            "custom_components.pc_user_statistics.config_flow.async_check_influxdb_connection",
            AsyncMock(return_value=(False, "cannot_connect"))
        ):
            result = await flow.async_step_user(user_input)

        call_kwargs = flow.async_show_form.call_args[1]
        assert "cannot_connect" in call_kwargs.get("errors", {}).get("base", "")


# ── OptionsFlow ────────────────────────────────────────────────────────────

class TestOptionsFlow:

    @pytest.mark.asyncio
    async def test_shows_form_on_first_call(self):
        from custom_components.pc_user_statistics.config_flow import OptionsFlow

        flow = OptionsFlow()
        flow.hass = MagicMock()
        entry = MagicMock()
        entry.options = {
            "tracked_users": ["flemming", "lukas"],
            "user_mappings": {"konge": "flemming"},  # dict, not string
        }
        flow.config_entry = entry
        flow.async_show_form = MagicMock(return_value={"type": "form"})

        result = await flow.async_step_init(None)
        flow.async_show_form.assert_called_once()

    @pytest.mark.asyncio
    async def test_saves_valid_options(self):
        from custom_components.pc_user_statistics.config_flow import OptionsFlow

        flow = OptionsFlow()
        flow.hass = MagicMock()
        entry = MagicMock()
        entry.options = {}
        flow.config_entry = entry
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

        user_input = {
            "tracked_users": "flemming, lukas",
            "user_mappings": "konge=flemming, lukas=lukas",
        }

        result = await flow.async_step_init(user_input)
        flow.async_create_entry.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_tracked_users_shows_error(self):
        from custom_components.pc_user_statistics.config_flow import OptionsFlow

        flow = OptionsFlow()
        flow.hass = MagicMock()
        entry = MagicMock()
        entry.options = {}
        flow.config_entry = entry
        flow.async_show_form = MagicMock(return_value={"type": "form"})

        user_input = {
            "tracked_users": "",
            "user_mappings": "",
        }

        result = await flow.async_step_init(user_input)
        call_kwargs = flow.async_show_form.call_args[1]
        errors = call_kwargs.get("errors", {})
        # Error key is on "tracked_users" field, not "base"
        assert "no_users" in errors.get("tracked_users", "") or "no_users" in errors.get("base", "")
