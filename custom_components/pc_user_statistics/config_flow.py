# File Name: config_flow.py
# Version: 2.4.1
# Description: Configuration flow and options flow for the PC User Statistics integration.
# Last Updated: March 2, 2026
#
# Fix in 2.4.1:
#   FIX: Removed OptionsFlow.__init__() and the config_entry parameter from
#        async_get_options_flow(). In HA 2024.x, config_entry is a read-only
#        property on the OptionsFlow base class — setting it manually raises:
#        AttributeError: property 'config_entry' of 'OptionsFlow' object has no setter
#        HA now injects config_entry automatically; the flow just uses self.config_entry.

import voluptuous as vol
import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
import aiohttp
import urllib.parse

from .const import (
    DOMAIN,
    DEFAULT_DATABASE,
    CONF_USER_MAPPINGS,
    CONF_TRACKED_USERS,
    DEFAULT_USER_MAP,
    DEFAULT_USERS,
)
from .helpers import validate_influxdb_config

_LOGGER = logging.getLogger(__name__)


async def async_check_influxdb_connection(
    hass: HomeAssistant,
    host: str,
    port: int,
    username: str,
    password: str,
    database: str,
) -> tuple[bool, str]:
    """Asynchronously check InfluxDB connection and database access.

    Returns:
        Tuple of (success, error_key)
    """
    is_valid, error_msg = validate_influxdb_config(host, port, database, username, password)
    if not is_valid:
        _LOGGER.error("Config validation failed: %s", error_msg)
        return False, "invalid_config"

    try:
        async with aiohttp.ClientSession() as session:
            # Step 1: ping
            try:
                async with session.get(
                    f"http://{host}:{port}/ping",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    if response.status != 204:
                        _LOGGER.error("InfluxDB ping failed: HTTP %s", response.status)
                        return False, "cannot_connect"
            except aiohttp.ClientError as err:
                _LOGGER.error("InfluxDB ping failed: %s", err)
                return False, "cannot_connect"

            # Step 2: verify database exists
            query = urllib.parse.urlencode({"q": "SHOW DATABASES"})
            auth  = aiohttp.BasicAuth(username, password)

            try:
                async with session.get(
                    f"http://{host}:{port}/query?{query}",
                    auth=auth,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    if response.status != 200:
                        _LOGGER.error("InfluxDB query failed: HTTP %s", response.status)
                        return False, "cannot_connect"

                    data = await response.json()

                    if (
                        not isinstance(data, dict)
                        or not data.get("results")
                        or not isinstance(data["results"], list)
                        or len(data["results"]) == 0
                    ):
                        _LOGGER.error("Invalid InfluxDB response structure: %s", data)
                        return False, "cannot_connect"

                    first_result = data["results"][0]
                    if not first_result.get("series") or not isinstance(first_result["series"], list):
                        _LOGGER.error("No series in InfluxDB response: %s", data)
                        return False, "cannot_connect"

                    first_series = first_result["series"][0]
                    if not first_series.get("values") or not isinstance(first_series["values"], list):
                        _LOGGER.error("No values in InfluxDB response: %s", data)
                        return False, "cannot_connect"

                    databases = [
                        db[0]
                        for db in first_series["values"]
                        if isinstance(db, list) and len(db) > 0
                    ]

                    if not databases:
                        _LOGGER.error("No databases found in InfluxDB")
                        return False, "cannot_connect"

                    if database not in databases:
                        _LOGGER.error(
                            "Database '%s' not found. Available: %s", database, databases
                        )
                        return False, "cannot_connect"

                    _LOGGER.info("Successfully connected to InfluxDB database '%s'", database)
                    return True, ""

            except aiohttp.ClientError as err:
                _LOGGER.error("InfluxDB database query failed: %s", err)
                return False, "cannot_connect"

    except Exception as err:
        _LOGGER.exception("Unexpected error checking InfluxDB connection: %s", err)
        return False, "unknown"


# ── String helpers ────────────────────────────────────────────────────────────

def _parse_user_mappings(raw: str) -> dict[str, str]:
    """Parse user mappings from a comma-separated string.

    Format: "sensor_state=user_id, sensor_state=user_id"
    Example: "konge=flemming, lukas=lukas, sebas=sebastian"

    Returns empty dict on parse failure.
    """
    result = {}
    for part in raw.split(","):
        part = part.strip()
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        key   = key.strip().lower()
        value = value.strip().lower()
        if key and value:
            result[key] = value
    return result


def _parse_tracked_users(raw: str) -> list[str]:
    """Parse tracked users from a comma-separated string.

    Example: "flemming, lukas, sebastian"
    """
    return [u.strip().lower() for u in raw.split(",") if u.strip()]


def _user_mappings_to_str(mappings: dict) -> str:
    """Convert user mappings dict to editable string.

    Handles both plain-string values and dict values (with user_id key)
    so the text field shows correctly even when ha_user dicts are stored.
    """
    parts = []
    for k, v in mappings.items():
        user_id = v.get("user_id", "") if isinstance(v, dict) else v
        if k and user_id:
            parts.append(f"{k}={user_id}")
    return ", ".join(parts)


def _tracked_users_to_str(users: list[str]) -> str:
    """Convert tracked users list to editable string."""
    return ", ".join(users)


# ── Config flow ───────────────────────────────────────────────────────────────

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for PC User Statistics."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "OptionsFlow":
        """Return options flow handler.

        FIX: No longer passes config_entry to OptionsFlow constructor.
        HA 2024+ injects it automatically via the base class property.
        """
        return OptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            success, error_key = await async_check_influxdb_connection(
                self.hass,
                user_input["host"],
                user_input["port"],
                user_input["username"],
                user_input["password"],
                user_input["database"],
            )

            if success:
                return self.async_create_entry(
                    title="PC User Statistics",
                    data=user_input,
                )
            else:
                errors["base"] = error_key

        data_schema = vol.Schema({
            vol.Required("host",     default="a0d7b954-influxdb"): str,
            vol.Required("port",     default=8086):                 int,
            vol.Required("database", default=DEFAULT_DATABASE):     str,
            vol.Required("username", default="homeassistant"):      str,
            vol.Required("password"):                               str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )


# ── Options flow ──────────────────────────────────────────────────────────────

class OptionsFlow(config_entries.OptionsFlow):
    """Handle options flow — allows editing users after initial setup.

    FIX: No __init__ — HA 2024+ injects config_entry as a read-only base
    class property. Defining __init__(self, config_entry) and then setting
    self.config_entry raises AttributeError because the property has no setter.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show and handle the options form."""
        errors: dict[str, str] = {}

        # Current values — prefer options, fall back to defaults
        current_mappings = self.config_entry.options.get(CONF_USER_MAPPINGS, DEFAULT_USER_MAP)
        current_users    = self.config_entry.options.get(CONF_TRACKED_USERS,  DEFAULT_USERS)

        if user_input is not None:
            new_mappings = _parse_user_mappings(user_input[CONF_USER_MAPPINGS])
            new_users    = _parse_tracked_users(user_input[CONF_TRACKED_USERS])

            if not new_users:
                errors[CONF_TRACKED_USERS] = "no_users"
            elif not all(v in new_users for v in new_mappings.values()):
                errors[CONF_USER_MAPPINGS] = "mapping_user_not_tracked"
            else:
                _LOGGER.info(
                    "Options updated — users: %s, mappings: %s",
                    new_users, new_mappings,
                )
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_USER_MAPPINGS: new_mappings,
                        CONF_TRACKED_USERS: new_users,
                    },
                )

            # On error, keep what the user typed
            current_mappings  = _parse_user_mappings(user_input[CONF_USER_MAPPINGS])
            current_users_str = user_input[CONF_TRACKED_USERS]
        else:
            current_users_str = _tracked_users_to_str(current_users)

        options_schema = vol.Schema({
            vol.Required(CONF_TRACKED_USERS, default=current_users_str):                      str,
            vol.Required(CONF_USER_MAPPINGS, default=_user_mappings_to_str(current_mappings)): str,
        })

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            errors=errors,
        )
