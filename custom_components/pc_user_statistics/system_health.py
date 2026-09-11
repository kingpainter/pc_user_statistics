# File Name: system_health.py
# Version: 2.13.0
# Description: System health platform for PC User Statistics.
#              Exposes integration state in Settings → System → Repairs → System Information.
# Last Updated: September 10, 2026
#
# Changes in 2.13.0:
#   FIX (crash): read cfg['host']/cfg['port'] with dict-subscript access —
#        on a v2.17.0+ config entry (data={}, InfluxDB removed) this raised
#        KeyError and broke the System Information panel entirely.
#        can_reach_influxdb/influxdb_host/write_buffer removed — no more
#        external DB to ping, no more write buffer to report.
#
# Changes in 2.12.1:
#   FIX: coordinator lookup now uses entry.runtime_data instead of
#        hass.data[DOMAIN][entry_id] (old pattern).

from __future__ import annotations

import time
from typing import Any

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, __version__


@callback
def async_register(
    hass: HomeAssistant,
    register: system_health.SystemHealthRegistration,
) -> None:
    """Register system health callbacks."""
    register.async_register_info(async_system_health_info)


async def async_system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Return system health info shown in Settings → System → Repairs → System Information."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return {"error": "Integration not configured"}

    entry = entries[0]
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is None:
        return {"error": "Integration not loaded"}

    # Format last update time — only show a time delta if a delta has
    # actually been applied. last_write_time is initialised to 0.0 at
    # startup (not time.time()) so that "aldrig" is only shown when nothing
    # has happened yet, not from the epoch anchor.
    last_write = getattr(coordinator, "last_write_time", 0.0)
    now_ts = time.time()

    if last_write and last_write > 0 and (now_ts - last_write) < 86400:
        # An update has occurred within the last 24 h — show relative time
        delta = now_ts - last_write
        if delta < 60:
            last_write_str = f"{int(delta)}s siden"
        elif delta < 3600:
            last_write_str = f"{int(delta // 60)}m siden"
        else:
            last_write_str = f"{int(delta // 3600)}t {int((delta % 3600) // 60)}m siden"
    elif not coordinator.current_user:
        # No active user — PC is idle, no updates expected
        last_write_str = "ingen aktiv session"
    else:
        last_write_str = "aldrig"

    # Monthly data status — human-readable string instead of raw bool
    if coordinator._monthly_loaded:
        monthly_str = "Indlæst ✓"
    else:
        monthly_str = "Indlæser..."

    return {
        "version": __version__,
        "data_source": "Home Assistant statistics",
        "monthly_data": monthly_str,
        "tracked_users": len(coordinator.tracked_users),
        "current_user": coordinator.current_user or "ingen",
        "last_update": last_write_str,
    }
