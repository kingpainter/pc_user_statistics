# File Name: websocket.py
# Version: 2.5.0
# Description: WebSocket API for the PC User Statistics panel.
# Last Updated: March 7, 2026

import logging
import voluptuous as vol
from homeassistant.core import HomeAssistant, callback
from homeassistant.components import websocket_api

from .const import DOMAIN, __version__

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


@websocket_api.websocket_command({"type": f"{DOMAIN}/get_stats"})
@callback
def ws_get_stats(hass, connection, msg):
    coordinator = _get_coordinator(hass)
    if not coordinator:
        connection.send_error(msg["id"], "not_ready", "Integration not ready"); return
    try:
        data = coordinator.data or {}
        connection.send_result(msg["id"], {
            "current_user": data.get("current_user"),
            "acc_time": data.get("acc_time", 0.0),
            "acc_energy": data.get("acc_energy", 0.0),
            "acc_cost": data.get("acc_cost", 0.0),
            "monthly": data.get("monthly", {}),
            "tracked_users": coordinator.tracked_users,
            "user_map": coordinator.user_map,
            "monthly_loaded": coordinator._monthly_loaded,
            "gauge1_value": data.get("gauge1_value"),
            "gauge1_unit": data.get("gauge1_unit"),
            "gauge1_label": data.get("gauge1_label"),
            "gauge2_value": data.get("gauge2_value"),
            "gauge2_unit": data.get("gauge2_unit"),
            "gauge2_label": data.get("gauge2_label"),
        })
    except Exception as err:
        connection.send_error(msg["id"], "unknown_error", str(err))


@websocket_api.websocket_command({"type": f"{DOMAIN}/get_system"})
@callback
def ws_get_system(hass, connection, msg):
    coordinator = _get_coordinator(hass)
    if not coordinator:
        connection.send_error(msg["id"], "not_ready", "Integration not ready"); return
    try:
        cfg = coordinator.config
        connection.send_result(msg["id"], {
            "version": __version__,
            "influxdb_host": cfg.get("host", "unknown"),
            "influxdb_port": cfg.get("port", 8086),
            "influxdb_database": cfg.get("database", "unknown"),
            "buffer_size": len(coordinator.failed_writes),
            "buffer_max": 100,
            "tracked_users": coordinator.tracked_users,
            "user_map": coordinator.user_map,
        })
    except Exception as err:
        connection.send_error(msg["id"], "unknown_error", str(err))


@websocket_api.websocket_command({"type": f"{DOMAIN}/get_notifications"})
@callback
def ws_get_notifications(hass, connection, msg):
    store = _get_store(hass)
    if not store:
        connection.send_error(msg["id"], "not_ready", "Store not ready"); return
    try:
        connection.send_result(msg["id"], {
            "rules": store.get_rules(),
            "devices": store.get_devices(),
            "available_devices": store.get_available_mobile_apps(hass),
        })
    except Exception as err:
        connection.send_error(msg["id"], "unknown_error", str(err))


@websocket_api.websocket_command({
    "type": f"{DOMAIN}/save_notification",
    vol.Required("rule_id"): str,
    vol.Required("config"): dict,
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
    vol.Required("user"): str,
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


@websocket_api.websocket_command({"type": f"{DOMAIN}/get_devices"})
@callback
def ws_get_devices(hass, connection, msg):
    store = _get_store(hass)
    if not store:
        connection.send_error(msg["id"], "not_ready", "Store not ready"); return
    try:
        connection.send_result(msg["id"], {
            "configured": store.get_devices(),
            "available": store.get_available_mobile_apps(hass),
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
    """Run InfluxDB GROUP BY time(1d) query and return structured data."""
    import aiohttp, urllib.parse
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
        async with aiohttp.ClientSession() as session:
            params = urllib.parse.urlencode({"q": query, "db": cfg["database"]})
            auth   = aiohttp.BasicAuth(cfg["username"], cfg["password"])
            async with session.get(
                f"http://{cfg['host']}:{cfg['port']}/query?{params}",
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return {"days": [], "users": [], "series": {}}
                data = await resp.json()
    except Exception as err:
        _LOGGER.warning("History query failed: %s", err)
        return {"days": [], "users": [], "series": {}}

    # Parse response
    # Structure: results[0].series[] each has tags.user + columns + values
    results = data.get("results", [{}])
    series_list = results[0].get("series", []) if results else []

    # Build a set of all day strings
    all_days: list[str] = []
    user_series: dict[str, dict[str, dict]] = {}  # user → {day → {time,energy,cost}}

    for s in series_list:
        user = s.get("tags", {}).get("user", "unknown")
        cols = s.get("columns", [])  # ["time","time","energy","cost"]
        vals = s.get("values", [])

        # find col indices
        try:
            t_idx = cols.index("time")
            tm_idx = cols.index("time", t_idx + 1) if cols.count("time") > 1 else 1
            e_idx  = cols.index("energy")
            c_idx  = cols.index("cost")
        except ValueError:
            tm_idx, e_idx, c_idx = 1, 2, 3

        user_series[user] = {}
        for row in vals:
            # row[0] is the timestamp e.g. "2026-02-01T00:00:00Z"
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

@websocket_api.websocket_command({
    "type": f"{DOMAIN}/get_config",
})
@callback
def ws_get_config(hass, connection, msg):
    """Return current integration configuration (data + options)."""
    coordinator = _get_coordinator(hass)
    if not coordinator:
        connection.send_error(msg["id"], "not_ready", "Integration not ready"); return
    try:
        entry = coordinator.config_entry
        connection.send_result(msg["id"], {
            # InfluxDB (from data — set at setup, not editable here)
            "host":           entry.data.get("host", ""),
            "port":           entry.data.get("port", 8086),
            "database":       entry.data.get("database", ""),
            "username":       entry.data.get("username", ""),
            # Sensor entity IDs (from data)
            "user_entity":          entry.data.get("user_entity",         "sensor.flemming_gamer_satellite_loggeduser"),
            "watt_entity":          entry.data.get("watt_entity",          "sensor.gamer_pc_power_monitor_current_consumption"),
            "device_power_entity":  entry.data.get("device_power_entity", "sensor.gamer_pc_power_monitor_device_power"),
            "price_entity":         entry.data.get("price_entity",        "sensor.energi_data_service"),
            # Optional gauge sensors (live display only, not stored in coordinator)
            "gauge1_entity":        entry.data.get("gauge1_entity", ""),
            "gauge1_label":         entry.data.get("gauge1_label", ""),
            "gauge1_max":           entry.data.get("gauge1_max", ""),
            "gauge2_entity":        entry.data.get("gauge2_entity", ""),
            "gauge2_label":         entry.data.get("gauge2_label", ""),
            "gauge2_max":           entry.data.get("gauge2_max", ""),
            "gauge3_entity":        entry.data.get("gauge3_entity", ""),
            "gauge3_label":         entry.data.get("gauge3_label", ""),
            "gauge3_max":           entry.data.get("gauge3_max", ""),
            "gauge4_entity":        entry.data.get("gauge4_entity", ""),
            "gauge4_label":         entry.data.get("gauge4_label", ""),
            "gauge4_max":           entry.data.get("gauge4_max", ""),
            "gauge5_entity":        entry.data.get("gauge5_entity", ""),
            "gauge5_label":         entry.data.get("gauge5_label", ""),
            "gauge5_max":           entry.data.get("gauge5_max", ""),
            # User config (from options — raw, so ha_user dict values are preserved)
            "user_mappings":  entry.options.get("user_mappings", coordinator.user_map),
            "tracked_users":  coordinator.tracked_users,
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
    vol.Optional("gauge1_entity"):       str,
    vol.Optional("gauge1_label"):        str,
    vol.Optional("gauge1_max"):          str,
    vol.Optional("gauge2_entity"):       str,
    vol.Optional("gauge2_label"):        str,
    vol.Optional("gauge2_max"):          str,
    vol.Optional("gauge3_entity"):       str,
    vol.Optional("gauge3_label"):        str,
    vol.Optional("gauge3_max"):          str,
    vol.Optional("gauge4_entity"):       str,
    vol.Optional("gauge4_label"):        str,
    vol.Optional("gauge4_max"):          str,
    vol.Optional("gauge5_entity"):       str,
    vol.Optional("gauge5_label"):        str,
    vol.Optional("gauge5_max"):          str,
})
@websocket_api.async_response
async def ws_save_config(hass, connection, msg):
    """Save user configuration and sensor entity IDs. Triggers integration reload."""
    coordinator = _get_coordinator(hass)
    if not coordinator:
        connection.send_error(msg["id"], "not_ready", "Integration not ready"); return
    try:
        entry = coordinator.config_entry

        # Validate inputs
        user_mappings = msg["user_mappings"]
        tracked_users = msg["tracked_users"]

        if not isinstance(user_mappings, dict) or not user_mappings:
            connection.send_error(msg["id"], "invalid_input", "user_mappings must be a non-empty dict"); return
        if not isinstance(tracked_users, list) or not tracked_users:
            connection.send_error(msg["id"], "invalid_input", "tracked_users must be a non-empty list"); return

        # Build new options (user config)
        from .const import CONF_USER_MAPPINGS, CONF_TRACKED_USERS
        new_options = {
            **entry.options,
            CONF_USER_MAPPINGS: user_mappings,
            CONF_TRACKED_USERS: tracked_users,
        }

        # Build new data (sensor entity IDs) — only update fields that were sent
        new_data = dict(entry.data)
        for field in ("user_entity", "watt_entity", "device_power_entity", "price_entity"):
            if field in msg and msg[field].strip():
                new_data[field] = msg[field].strip()
        # Gauge sensors — allow empty string to clear
        for field in ("gauge1_entity", "gauge1_label", "gauge1_max",
                      "gauge2_entity", "gauge2_label", "gauge2_max",
                      "gauge3_entity", "gauge3_label", "gauge3_max",
                      "gauge4_entity", "gauge4_label", "gauge4_max",
                      "gauge5_entity", "gauge5_label", "gauge5_max"):
            if field in msg:
                new_data[field] = msg[field].strip()

        # Save both — this triggers _async_options_updated → reload
        hass.config_entries.async_update_entry(entry, data=new_data, options=new_options)

        _LOGGER.info("Configuration saved — integration will reload")
        connection.send_result(msg["id"], {"success": True, "reload": True})

    except Exception as err:
        _LOGGER.exception("Error saving config: %s", err)
        connection.send_error(msg["id"], "unknown_error", str(err))
