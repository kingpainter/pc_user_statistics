# File Name: diagnostics.py
# Version: 2.6.2
# Description: Diagnostics support for PC User Statistics integration.
#              Allows users to download debug info from HA UI (Gold quality scale requirement).
# Last Updated: March 7, 2026

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, __version__


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Sensitive values (password) are redacted automatically by HA.
    """
    coordinator = None
    for value in hass.data.get(DOMAIN, {}).values():
        if hasattr(value, "tracked_users"):
            coordinator = value
            break

    coordinator_data: dict[str, Any] = {}
    if coordinator:
        data = coordinator.data or {}
        coordinator_data = {
            "tracked_users": coordinator.tracked_users,
            "monthly_loaded": coordinator._monthly_loaded,
            "current_user": data.get("current_user"),
            "acc_time": data.get("acc_time", 0.0),
            "acc_energy": data.get("acc_energy", 0.0),
            "acc_cost": data.get("acc_cost", 0.0),
            "monthly_users": list(data.get("monthly", {}).keys()),
            "update_interval_seconds": coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None,
            "last_update_success": coordinator.last_update_success,
        }

    return {
        "integration_version": __version__,
        "config_entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "state": entry.state.value,
            "source": entry.source,
            "host": entry.data.get("host"),
            "port": entry.data.get("port"),
            "database": entry.data.get("database"),
            "username": entry.data.get("username"),
            # password intentionally omitted
        },
        "options": {
            "tracked_users": entry.options.get("tracked_users", []),
            # user_map omitted — may contain HA user IDs (privacy)
        },
        "coordinator": coordinator_data,
    }
