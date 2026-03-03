# File Name: websocket.py
# Version: 2.4.1
# Description: WebSocket API for the PC User Statistics panel.
# Last Updated: March 2, 2026
#
# Fixes in 2.4.1:
#   FIX 1: ws_save_config — send_result BEFORE scheduling reload via async_create_task.
#           Previously async_update_entry triggered a synchronous reload that killed
#           the WebSocket connection before the response could be sent → crash + no save.
#   FIX 2: ws_get_config — return raw user_mappings from entry.options (preserves ha_user
#           objects), not coordinator.user_map (which strips ha_user after normalization).
#   FIX 3: _query_history — use coordinator's persistent HTTP session instead of
#           creating a new aiohttp.ClientSession per call.

import logging
import voluptuous as vol
from homeassistant.core import HomeAssistant, callback
from homeassistant.components import websocket_api

from .const import DOMAIN, CONF_USER_MAPPINGS, CONF_TRACKED_USERS, __version__

_LOGGER = logging.getLogger(__name__)


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register all WebSocket commands for the panel."""
    websocket_api.async_register_command(hass, ws_get_stats)
    websocket_api.async_register_command(hass, ws_get_system)
    websocket_api.async_register_command(hass, ws_get_notifications)
    websocket_api.async_register_command(hass, ws_save_notification)
    websocket_api.async_register_command(hass, ws_delete_notification)
    websocket_api.async_register_command(hass, ws_test_notification)
    websocket_api.async_register_command(hass, ws_get_devices)
    websocket_api.async_register_command(hass, ws_save_devices)
    websocket_api.async_register_command(hass, ws_get_history)
    websocket_api.async_register_command(hass, ws_get_config)
    websocket_api.async_register_command(hass, ws_save_config)
    _LOGGER.info("PC User Statistics WebSocket API registered (11 commands)")


def _get_coordinator(hass):
    for value in hass.data.get(DOMAIN, {}).values():
        if hasattr(value, "tracked_users"):
            return value
    return None

def _get_store(hass):
    return hass.data.get(DOMAIN, {}).get("store")

def _get_notification_manager(hass):
    return hass.data.get(DOMAIN, {}).get("notification_manager")


# ── Stats ─────────────────────────────────────────────────────────────────────

@websocket_api.websocket_command({"type": f"{DOMAIN}/get_stats"})
@callback
def ws_get_stats(hass, connection, msg):
    coordinator = _get_coordinator(hass)
    if not coordinator:
        connection.send_error(msg["id"], "not_ready", "Integration not ready"); return
    try:
        data = coordinator.data or {}
        connection.send_result(msg["id"], {
            "current_user":  data.get("current_user"),
            "acc_time":      data.get("acc_time",   0.0),
            "acc_energy":    data.get("acc_energy", 0.0),
            "acc_cost":      data.get("acc_cost",   0.0),
            "monthly":       data.get("monthly",    {}),
            "tracked_users": coordinator.tracked_users,
            "user_map":      coordinator.user_map,
        })
    except Exception as err:
        connection.send_error(msg["id"], "unknown_error", str(err))


# ── System ────────────────────────────────────────────────────────────────────

@websocket_api.websocket_command({"type": f"{DOMAIN}/get_system"})
@callback
def ws_get_system(hass, connection, msg):
    coordinator = _get_coordinator(hass)
    if not coordinator:
        connection.send_error(msg["id"], "not_ready", "Integration not ready"); return
    try:
        cfg = coordinator.config
        connection.send_result(msg["id"], {
            "version":            __version__,
            "influxdb_host":      cfg.get("host", "unknown"),
            "influxdb_port":      cfg.get("port", 8086),
            "influxdb_database":  cfg.get("database", "unknown"),
            "buffer_size":        len(coordinator.failed_writes),
            "buffer_max":         100,
            "tracked_users":      coordinator.tracked_users,
            "user_map":           coordinator.user_map,
        })
    except Exception as err:
        connection.send_error(msg["id"], "unknown_error", str(err))


# ── Notifications ─────────────────────────────────────────────────────────────

@websocket_api.websocket_command({"type": f"{DOMAIN}/get_notifications"})
@callback
def ws_get_notifications(hass, connection, msg):
    store = _get_store(hass)
    if not store:
        connection.send_error(msg["id"], "not_ready", "Store not ready"); return
    try:
        connection.send_result(msg["id"], {
            "rules":             store.get_rules(),
            "devices":           store.get_devices(),
            "available_devices": store.get_available_mobile_apps(hass),
        })
    except Exception as err:
        connection.send_error(msg["id"], "unknown_error", str(err))


@websocket_api.websocket_command({
    "type": f"{DOMAIN}/save_notification",
    vol.Required("rule_id"): str,
    vol.Required("config"):  dict,
})
@websocket_api.async_response
async def ws_save_notification(hass, connection, msg):
    store = _get_store(hass)
    if not store:
        connection.send_error(msg["id"], "not_ready", "Store not ready"); return
    try:
        await store.async_save_rule(msg["rule_id"], msg["config"])
        connection.send_result(msg["id"], {"success": True})
    except Exception as err:
        connection.send_error(msg["id"], "unknown_error", str(err))


@websocket_api.websocket_command({
    "type": f"{DOMAIN}/delete_notification",
    vol.Required("rule_id"): str,
})
@websocket_api.async_response
async def ws_delete_notification(hass, connection, msg):
    store = _get_store(hass)
    if not store:
        connection.send_error(msg["id"], "not_ready", "Store not ready"); return
    try:
        deleted = await store.async_delete_rule(msg["rule_id"])
        if not deleted:
            connection.send_error(msg["id"], "cannot_delete", "Premade rules cannot be deleted"); return
        connection.send_result(msg["id"], {"success": True})
    except Exception as err:
        connection.send_error(msg["id"], "unknown_error", str(err))


@websocket_api.websocket_command({
    "type": f"{DOMAIN}/test_notification",
    vol.Required("rule_id"): str,
    vol.Required("user"):    str,
})
@websocket_api.async_response
async def ws_test_notification(hass, connection, msg):
    nm = _get_notification_manager(hass)
    if not nm:
        connection.send_error(msg["id"], "not_ready", "Notification manager not ready"); return
    try:
        ok = await nm.async_send_test(msg["rule_id"], msg["user"])
        if not ok:
            connection.send_error(msg["id"], "send_failed", "No devices or rule not found"); return
        connection.send_result(msg["id"], {"success": True})
    except Exception as err:
        connection.send_error(msg["id"], "unknown_error", str(err))


# ── Devices ───────────────────────────────────────────────────────────────────

@websocket_api.websocket_command({"type": f"{DOMAIN}/get_devices"})
@callback
def ws_get_devices(hass, connection, msg):
    store = _get_store(hass)
    if not store:
        connection.send_error(msg["id"], "not_ready", "Store not ready"); return
    try:
        connection.send_result(msg["id"], {
            "configured": store.get_devices(),
            "available":  store.get_available_mobile_apps(hass),
        })
    except Exception as err:
        connection.send_error(msg["id"], "unknown_error", str(err))


@websocket_api.websocket_command({
    "type": f"{DOMAIN}/save_devices",
    vol.Required("devices"): list,
})
@websocket_api.async_response
async def ws_save_devices(hass, connection, msg):
    store = _get_store(hass)
    if not store:
        connection.send_error(msg["id"], "not_ready", "Store not ready"); return
    try:
        await store.async_save_devices(msg["devices"])
        connection.send_result(msg["id"], {"success": True})
    except Exception as err:
        connection.send_error(msg["id"], "unknown_error", str(err))


# ── History ───────────────────────────────────────────────────────────────────

@websocket_api.websocket_command({
    "type": f"{DOMAIN}/get_history",
    vol.Optional("days", default=30): int,
})
@websocket_api.async_response
async def ws_get_history(hass, connection, msg):
    """Query InfluxDB for daily totals per user over the last N days."""
    coordinator = _get_coordinator(hass)
    if not coordinator:
        connection.send_error(msg["id"], "not_ready", "Integration not ready")
        return
    try:
        days = min(msg.get("days", 30), 90)  # cap at 90
        result = await _query_history(coordinator, days)
        connection.send_result(msg["id"], result)
    except Exception as err:
        _LOGGER.exception("Error getting history: %s", err)
        connection.send_error(msg["id"], "unknown_error", str(err))


async def _query_history(coordinator, days: int) -> dict:
    """Run InfluxDB GROUP BY time(1d) query and return structured data.

    FIX 3: Uses coordinator's persistent HTTP session instead of creating
    a new aiohttp.ClientSession on every call (was wasteful and inconsistent).
    """
    import urllib.parse
    from datetime import datetime, timedelta, timezone

    cfg = coordinator.config
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")

    query = (
        f'SELECT SUM("time_delta") AS "time", '
        f'SUM("energy_delta") AS "energy", '
        f'SUM("cost_delta") AS "cost" '
        f'FROM pc_usage '
        f'WHERE time >= \'{start}\' '
        f'GROUP BY time(1d), "user" fill(0)'
    )

    try:
        # FIX 3: reuse the coordinator's persistent session (no new ClientSession)
        params = urllib.parse.urlencode({"q": query, "db": cfg["database"]})
        async with coordinator._http_session.get(
            f"http://{cfg['host']}:{cfg['port']}/query?{params}",
        ) as resp:
            if resp.status != 200:
                return {"days": [], "users": [], "series": {}}
            data = await resp.json()
    except Exception as err:
        _LOGGER.warning("History query failed: %s", err)
        return {"days": [], "users": [], "series": {}}

    results     = data.get("results", [{}])
    series_list = results[0].get("series", []) if results else []

    all_days:    list[str]                    = []
    user_series: dict[str, dict[str, dict]]   = {}

    for s in series_list:
        user = s.get("tags", {}).get("user", "unknown")
        cols = s.get("columns", [])
        vals = s.get("values",  [])

        try:
            t_idx  = cols.index("time")
            tm_idx = cols.index("time", t_idx + 1) if cols.count("time") > 1 else 1
            e_idx  = cols.index("energy")
            c_idx  = cols.index("cost")
        except ValueError:
            tm_idx, e_idx, c_idx = 1, 2, 3

        user_series[user] = {}
        for row in vals:
            day = row[0][:10] if row[0] else ""
            if not day:
                continue
            if day not in all_days:
                all_days.append(day)
            user_series[user][day] = {
                "time":   float(row[tm_idx] or 0),
                "energy": float(row[e_idx]  or 0),
                "cost":   float(row[c_idx]  or 0),
            }

    all_days.sort()
    return {
        "days":   all_days,
        "users":  list(user_series.keys()),
        "series": user_series,
    }


# ── Configuration editor ──────────────────────────────────────────────────────

@websocket_api.websocket_command({"type": f"{DOMAIN}/get_config"})
@callback
def ws_get_config(hass, connection, msg):
    """Return current integration configuration (data + options).

    FIX 2: Returns raw user_mappings from entry.options, NOT coordinator.user_map.
    coordinator.user_map is normalized (ha_user stripped to plain string).
    The panel needs the full dict {user_id, ha_user} to pre-fill the HA-bruger dropdown.
    """
    coordinator = _get_coordinator(hass)
    if not coordinator:
        connection.send_error(msg["id"], "not_ready", "Integration not ready"); return
    try:
        entry = coordinator.config_entry
        # FIX 2: read from options (raw, preserves ha_user dicts), not coordinator.user_map
        raw_mappings  = entry.options.get(CONF_USER_MAPPINGS, coordinator.user_map)
        raw_tracked   = entry.options.get(CONF_TRACKED_USERS, coordinator.tracked_users)

        connection.send_result(msg["id"], {
            # InfluxDB connection (read-only in panel — changed via config flow)
            "host":                 entry.data.get("host", ""),
            "port":                 entry.data.get("port", 8086),
            "database":             entry.data.get("database", ""),
            "username":             entry.data.get("username", ""),
            # Sensor entity IDs
            "user_entity":          entry.data.get("user_entity",         ""),
            "watt_entity":          entry.data.get("watt_entity",          ""),
            "device_power_entity":  entry.data.get("device_power_entity", ""),
            "price_entity":         entry.data.get("price_entity",        ""),
            # User config — raw from options so ha_user is preserved
            "user_mappings":        raw_mappings,
            "tracked_users":        raw_tracked,
        })
    except Exception as err:
        connection.send_error(msg["id"], "unknown_error", str(err))


@websocket_api.websocket_command({
    "type": f"{DOMAIN}/save_config",
    vol.Required("user_mappings"): dict,
    vol.Required("tracked_users"): list,
    vol.Optional("user_entity"):         str,
    vol.Optional("watt_entity"):         str,
    vol.Optional("device_power_entity"): str,
    vol.Optional("price_entity"):        str,
})
@websocket_api.async_response
async def ws_save_config(hass, connection, msg):
    """Save user configuration and sensor entity IDs.

    FIX 1: Send WebSocket result BEFORE triggering integration reload.
    Previously async_update_entry fired _async_options_updated synchronously,
    which unloaded the integration while the WS response was still pending.
    Result: connection died, JS callWS() never resolved, panel crashed.

    Fix: send_result first, then schedule reload via hass.async_create_task()
    so it runs after the current event loop iteration completes.
    """
    coordinator = _get_coordinator(hass)
    if not coordinator:
        connection.send_error(msg["id"], "not_ready", "Integration not ready"); return
    try:
        entry = coordinator.config_entry

        user_mappings = msg["user_mappings"]
        tracked_users = msg["tracked_users"]

        if not isinstance(user_mappings, dict) or not user_mappings:
            connection.send_error(msg["id"], "invalid_input", "user_mappings must be a non-empty dict"); return
        if not isinstance(tracked_users, list) or not tracked_users:
            connection.send_error(msg["id"], "invalid_input", "tracked_users must be a non-empty list"); return

        # Build new options — preserve ha_user dicts as-is (coordinator normalizes on load)
        new_options = {
            **entry.options,
            CONF_USER_MAPPINGS: user_mappings,
            CONF_TRACKED_USERS: tracked_users,
        }

        # Build new data — only update sensor entity ID fields that were sent
        new_data = dict(entry.data)
        for field in ("user_entity", "watt_entity", "device_power_entity", "price_entity"):
            val = msg.get(field, "")
            if val and val.strip():
                new_data[field] = val.strip()

        # Persist the new config entry (does NOT trigger reload by itself)
        hass.config_entries.async_update_entry(entry, data=new_data, options=new_options)
        _LOGGER.info("Configuration saved — scheduling integration reload")

        # FIX 1: Send success to the panel BEFORE reload kills the WS connection
        connection.send_result(msg["id"], {"success": True, "reload": True})

        # Schedule reload asynchronously — runs after this coroutine returns,
        # so the WS response above is guaranteed to be sent first.
        async def _do_reload():
            await hass.config_entries.async_reload(entry.entry_id)

        hass.async_create_task(_do_reload())

    except Exception as err:
        _LOGGER.exception("Error saving config: %s", err)
        connection.send_error(msg["id"], "unknown_error", str(err))
