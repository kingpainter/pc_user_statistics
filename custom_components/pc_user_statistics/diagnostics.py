# File Name: diagnostics.py
# Version: 2.5.3
# Description: Diagnostics for PC User Statistics — Gold quality scale requirement.
#              Config entry + per-device diagnostics downloadable from HA UI.
#              Credentials are explicitly redacted via async_redact_data.
# Last Updated: March 6, 2026
#
# Changes in 2.5.3:
#   FIX: async_redact_data now used explicitly for entry.data — HA does NOT
#        redact credentials automatically; we must call it ourselves.
#   ADD: async_get_device_diagnostics — per-device (hub + per-user) debug info.
#   ADD: _pending, _idle_since, last_write_time added to coordinator snapshot.
#   ADD: failed_writes timestamps included (no PII — just nanosecond timestamps).

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, __version__

# Fields to redact from entry.data before including in diagnostics output.
# HA does NOT redact these automatically — we must call it ourselves.
TO_REDACT = {"password", "username", "token", "api_key"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Accessible via Settings → Devices & Services → PC User Statistics → three-dot menu → Download diagnostics.
    """
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    store       = hass.data.get(DOMAIN, {}).get("store")
    now_ts      = datetime.now(timezone.utc).timestamp()

    # ── Coordinator state ──────────────────────────────────────────────────
    coordinator_info: dict[str, Any] = {"available": False}
    if coordinator:
        lw = coordinator.last_write_time
        last_write_age = f"{int(now_ts - lw)}s ago" if lw else "never"

        idle = coordinator._idle_since
        idle_age = f"{int(now_ts - idle)}s ago" if idle else "not idle"

        coordinator_info = {
            "available":      True,
            "current_user":   coordinator.current_user,
            "monthly_loaded": coordinator._monthly_loaded,
            "tracked_users":  coordinator.tracked_users,
            "user_map":       coordinator.user_map,
            "last_month":     coordinator.last_month,
            "last_write":     last_write_age,
            "idle_since":     idle_age,
            "buffer_size":    len(coordinator.failed_writes),
            "buffer_max":     100,
            "failed_write_timestamps": [
                w.get("timestamp") for w in coordinator.failed_writes
            ],
            "session": {
                "acc_time_s":     round(coordinator.acc_time, 1),
                "acc_energy_kwh": round(coordinator.acc_energy, 4),
                "acc_cost_dkk":   round(coordinator.acc_cost, 2),
            },
            "monthly": {
                user: {k: round(v, 2) for k, v in vals.items()}
                for user, vals in coordinator.monthly.items()
            },
            "pending": {
                user: {k: round(v, 2) for k, v in vals.items()}
                for user, vals in coordinator._pending.items()
            } if not coordinator._monthly_loaded else {},
        }

    # ── Notification store ─────────────────────────────────────────────────
    store_info: dict[str, Any] = {"available": False}
    if store:
        rules = store.get_rules()
        store_info = {
            "available":          True,
            "rule_count":         len(rules),
            "devices_configured": len(store.get_devices()),
            "rules": {
                rule_id: {
                    "name":            r.get("name", ""),
                    "trigger_type":    r.get("trigger_type", ""),
                    "trigger_value":   r.get("trigger_value"),
                    "enabled":         r.get("enabled", False),
                    "repeat":          r.get("repeat", False),
                    "repeat_interval": r.get("repeat_interval", 0),
                }
                for rule_id, r in rules.items()
            },
        }

    # ── Config entry — credentials explicitly redacted ─────────────────────
    # async_redact_data replaces keys in TO_REDACT with "**REDACTED**".
    # HA does NOT do this automatically — we must call it ourselves.
    config_info = async_redact_data(
        {
            "host":                entry.data.get("host", ""),
            "port":                entry.data.get("port", 8086),
            "database":            entry.data.get("database", ""),
            "username":            entry.data.get("username", ""),
            "password":            entry.data.get("password", ""),
            "user_entity":         entry.data.get("user_entity", ""),
            "watt_entity":         entry.data.get("watt_entity", ""),
            "device_power_entity": entry.data.get("device_power_entity", ""),
            "price_entity":        entry.data.get("price_entity", ""),
        },
        TO_REDACT,
    )

    return {
        "integration_version": __version__,
        "entry_id":            entry.entry_id,
        "config":              config_info,
        "coordinator":         coordinator_info,
        "store":               store_info,
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device: dr.DeviceEntry,
) -> dict[str, Any]:
    """Return diagnostics for a specific device (hub or per-user).

    Hub device:  live session state + write buffer.
    User device: that user's monthly totals + session if active.
    """
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not coordinator:
        return {"error": "Coordinator not available"}

    device_id = next(
        (ident[1] for ident in device.identifiers if ident[0] == DOMAIN),
        None,
    )

    now_ts = datetime.now(timezone.utc).timestamp()

    if device_id == "statistics_hub":
        lw = coordinator.last_write_time
        return {
            "device":         "hub",
            "current_user":   coordinator.current_user,
            "monthly_loaded": coordinator._monthly_loaded,
            "last_write":     f"{int(now_ts - lw)}s ago" if lw else "never",
            "session": {
                "acc_time_s":     round(coordinator.acc_time, 1),
                "acc_energy_kwh": round(coordinator.acc_energy, 4),
                "acc_cost_dkk":   round(coordinator.acc_cost, 2),
            },
            "write_buffer": {
                "size":       len(coordinator.failed_writes),
                "max":        100,
                "timestamps": [w.get("timestamp") for w in coordinator.failed_writes],
            },
        }

    # Per-user device
    user = device_id
    monthly = coordinator.monthly.get(user, {})
    pending = coordinator._pending.get(user, {}) if not coordinator._monthly_loaded else {}
    is_active = coordinator.current_user == user

    return {
        "device":         "user",
        "user":           user,
        "active_session": is_active,
        "monthly":        {k: round(v, 2) for k, v in monthly.items()},
        "pending":        {k: round(v, 2) for k, v in pending.items()},
        "session": {
            "acc_time_s":     round(coordinator.acc_time, 1),
            "acc_energy_kwh": round(coordinator.acc_energy, 4),
            "acc_cost_dkk":   round(coordinator.acc_cost, 2),
        } if is_active else {},
    }
