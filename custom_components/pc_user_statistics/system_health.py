# File Name: system_health.py
# Version: 2.5.3
# Description: System health platform for PC User Statistics.
#              Exposes integration state in Settings → System → Repairs → System Information.
# Last Updated: March 6, 2026

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, __version__

_PING_PATH = "/ping"


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

    coordinator = hass.data.get(DOMAIN, {}).get(entries[0].entry_id)
    if coordinator is None:
        return {"error": "Integration not loaded"}

    cfg = coordinator.config
    influx_url = f"http://{cfg['host']}:{cfg['port']}{_PING_PATH}"

    # Format last write time as human-readable
    last_write = coordinator.last_write_time
    if last_write:
        delta = datetime.now(timezone.utc).timestamp() - last_write
        if delta < 60:
            last_write_str = f"{int(delta)}s siden"
        elif delta < 3600:
            last_write_str = f"{int(delta // 60)}m siden"
        else:
            last_write_str = f"{int(delta // 3600)}t {int((delta % 3600) // 60)}m siden"
    else:
        last_write_str = "aldrig"

    return {
        "version": __version__,
        # async_check_can_reach_url shows a spinner in the UI until resolved
        "can_reach_influxdb": system_health.async_check_can_reach_url(hass, influx_url),
        "influxdb_host": f"{cfg['host']}:{cfg['port']}",
        "monthly_data_loaded": coordinator._monthly_loaded,
        "write_buffer": f"{len(coordinator.failed_writes)}/100",
        "tracked_users": len(coordinator.tracked_users),
        "current_user": coordinator.current_user or "ingen",
        "last_influxdb_write": last_write_str,
    }
