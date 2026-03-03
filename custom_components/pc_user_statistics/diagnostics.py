# File Name: diagnostics.py
# Version: 2.5.0
# Description: Diagnostics support for PC User Statistics — Gold quality scale requirement.
#              Allows users to download debug info from Settings → Devices & Services.
# Last Updated: March 3, 2026

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

    Accessible via Settings → Devices & Services → PC User Statistics → ⋮ → Download diagnostics.
    Passwords and sensitive credentials are redacted automatically by HA before download.
    """
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    store       = hass.data.get(DOMAIN, {}).get("store")

    # ── Coordinator state ──────────────────────────────────────────────────
    coordinator_info: dict[str, Any] = {"available": False}
    if coordinator:
        coordinator_info = {
            "available":        True,
            "current_user":     coordinator.current_user,
            "monthly_loaded":   coordinator._monthly_loaded,
            "tracked_users":    coordinator.tracked_users,
            "user_map":         coordinator.user_map,
            "last_month":       coordinator.last_month,
            "buffer_size":      len(coordinator.failed_writes),
            "buffer_max":       100,
            "session": {
                "acc_time_s":    round(coordinator.acc_time, 1),
                "acc_energy_kwh": round(coordinator.acc_energy, 4),
                "acc_cost_dkk":  round(coordinator.acc_cost, 2),
            },
            "monthly": {
                user: {k: round(v, 2) for k, v in vals.items()}
                for user, vals in coordinator.monthly.items()
            },
        }

    # ── Notification store ─────────────────────────────────────────────────
    store_info: dict[str, Any] = {"available": False}
    if store:
        rules   = store.get_rules()
        devices = store.get_devices()
        store_info = {
            "available":    True,
            "rule_count":   len(rules),
            "device_count": len(devices),
            "rules": {
                rule_id: {
                    "name":         r.get("name", ""),
                    "trigger_type": r.get("trigger_type", ""),
                    "enabled":      r.get("enabled", False),
                    "repeat":       r.get("repeat", False),
                }
                for rule_id, r in rules.items()
            },
            # Redact actual device service paths — just count them
            "devices_configured": len(devices),
        }

    # ── Config entry (credentials redacted by HA) ──────────────────────────
    config_info = {
        "host":     entry.data.get("host", ""),
        "port":     entry.data.get("port", 8086),
        "database": entry.data.get("database", ""),
        # username/password redacted by HA diagnostics framework
        "user_entity":         entry.data.get("user_entity", ""),
        "watt_entity":         entry.data.get("watt_entity", ""),
        "device_power_entity": entry.data.get("device_power_entity", ""),
        "price_entity":        entry.data.get("price_entity", ""),
    }

    return {
        "integration_version": __version__,
        "entry_id":            entry.entry_id,
        "config":              config_info,
        "coordinator":         coordinator_info,
        "store":               store_info,
    }
