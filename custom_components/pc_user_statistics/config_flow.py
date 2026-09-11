# File Name: config_flow.py
# Version: 2.7.0
# Description: Configuration flow and options flow for the PC User Statistics integration.
# Last Updated: September 10, 2026
#
# Changes in 2.7.0:
#   InfluxDB/VictoriaMetrics connection step removed (v2.17.0 — data now
#   comes from HA's own recorder). async_check_influxdb_connection() and the
#   host/port/database/username/password form deleted; async_step_user() is
#   now a plain confirm-and-create step. async_step_reconfigure() removed —
#   there is no longer any connection config to reconfigure. Existing config
#   entries keep their old (now-unused) InfluxDB data keys harmlessly; they
#   are simply never read again.

import voluptuous as vol
import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_USER_MAPPINGS,
    CONF_TRACKED_USERS,
    DEFAULT_USER_MAP,
    DEFAULT_USERS,
)

_LOGGER = logging.getLogger(__name__)


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
        """Handle the initial step.

        No connection to configure anymore (v2.17.0) — just confirm and
        create the entry. User mappings / tracked users are set afterwards
        via the options flow (Settings → Devices & Services → PC User
        Statistics → Configure).
        """
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title="PC User Statistics", data={})

        return self.async_show_form(step_id="user")


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
