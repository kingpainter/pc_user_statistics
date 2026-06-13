# File Name: websocket.py
# Version: 3.1.0
# Description: WebSocket API for the PC User Statistics panel.
# Last Updated: June 13, 2026
#
# Changes in 3.1.0:
#   FIX 1B: _get_coordinator() now reads entry.runtime_data via
#        hass.config_entries.async_entries(DOMAIN) instead of duck-typing
#        on hass.data[DOMAIN].values(). Requires Fix 1A in __init__.py
#        (entry.runtime_data = coordinator).
#   FIX 3: ws_get_health now exposes flush_timer_active and flush_interval_s
#        so the Admin tab can show a green/red "periodisk backup aktiv"
#        indicator.
#
# Changes in 3.0.0:
#   NEW: ws_get_family_safety command — reads Microsoft Family Safety
#        entities (screen_time, balance, account_info, pending_requests)
#        directly from HA states and returns structured data per user.
#   NEW: get_config / save_config extended with family_safety_mappings
#        (user_id → FS entity prefix, stored in config entry data).

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
    websocket_api.async_register_command(hass, ws_get_health)
    websocket_api.async_register_command(hass, ws_get_family_safety)
    websocket_api.async_register_command(hass, ws_save_family_safety)
    websocket_api.async_register_command(hass, ws_get_notifications)
    websocket_api.async_register_command(hass, ws_save_notification)
    websocket_api.async_register_command(hass, ws_delete_notification)
    websocket_api.async_register_command(hass, ws_test_notification)
    websocket_api.async_register_command(hass, ws_get_devices)
    websocket_api.async_register_command(hass, ws_save_devices)
    websocket_api.async_register_command(hass, ws_get_history)
    websocket_api.async_register_command(hass, ws_get_config)
    websocket_api.async_register_command(hass, ws_save_config)
    _LOGGER.info("PC User Statistics WebSocket API registered (14 commands)")


def _get_coordinator(hass):
    """Return the active PCStatisticsCoordinator via entry.runtime_data.

    Fix 1B: previously iterated hass.data[DOMAIN].values() and duck-typed on
    tracked_users to find the coordinator — fragile and not aligned with
    modern HA practice. entry.runtime_data is set in async_setup_entry
    (Fix 1A) right after the coordinator is ready.
    """
    for entry in hass.config_entries.async_entries(DOMAIN):
        if getattr(entry, "runtime_data", None) is not None:
            return entry.runtime_data
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
        cfg = dict(coordinator.config) if coordinator.config else {}
        import time as _time
        now = _time.time()
        try:
            last_write = float(coordinator.last_write_time or 0)
        except (TypeError, ValueError):
            last_write = 0.0
        if last_write > 0 and (now - last_write) < 86400:
            delta = now - last_write
            if delta < 60:
                last_write_str = f"{int(delta)}s siden"
            elif delta < 3600:
                last_write_str = f"{int(delta // 60)}m siden"
            else:
                last_write_str = f"{int(delta // 3600)}t {int((delta % 3600) // 60)}m siden"
        else:
            try:
                last_write_str = "ingen aktiv session" if not coordinator.current_user else "aldrig"
            except Exception:
                last_write_str = "ukendt"

        monthly_str = "Indlæst ✓" if coordinator._monthly_loaded else "Afventer InfluxDB..."

        connection.send_result(msg["id"], {
            "version": __version__,
            "influxdb_host": cfg.get("host", "unknown"),
            "influxdb_port": cfg.get("port", 8086),
            "influxdb_database": cfg.get("database", "unknown"),
            "buffer_size": len(coordinator.failed_writes),
            "buffer_max": 100,
            "tracked_users": coordinator.tracked_users,
            "user_map": coordinator.user_map,
            "current_user": coordinator.current_user or "ingen",
            "monthly_loaded": coordinator._monthly_loaded,
            "monthly_data": monthly_str,
            "last_write": last_write_str,
        })
    except Exception as err:
        connection.send_error(msg["id"], "unknown_error", str(err))


@websocket_api.websocket_command({"type": f"{DOMAIN}/get_health"})
@callback
def ws_get_health(hass, connection, msg):
    """Return detailed health/state data for the Admin tab health widget."""
    coordinator = _get_coordinator(hass)
    store = _get_store(hass)
    if not coordinator:
        connection.send_error(msg["id"], "not_ready", "Integration not ready")
        return
    try:
        import time as _time
        now = _time.time()

        # ── Session snapshot info ──────────────────────────────────────────────
        snapshot_age_s = None
        snapshot_user = None
        snapshot_acc_time = None
        if store:
            snap = store.get_session()
            if snap:
                snapshot_age_s = int(now - snap.get("saved_at", now))
                snapshot_user = snap.get("current_user")
                snapshot_acc_time = snap.get("acc_time", 0.0)

        # ── Periodic flush info ───────────────────────────────────────────────
        last_flush = getattr(coordinator, "_last_session_flush", 0.0)
        flush_age_s = int(now - last_flush) if last_flush > 0 else None

        # ── InfluxDB write info ───────────────────────────────────────────────
        last_write = float(getattr(coordinator, "last_write_time", 0.0) or 0)
        write_age_s = int(now - last_write) if last_write > 0 else None
        consec_failures = getattr(coordinator, "_consecutive_write_failures", 0)

        connection.send_result(msg["id"], {
            # Session
            "current_user":      coordinator.current_user,
            "acc_time":          coordinator.acc_time,
            "snapshot_age_s":    snapshot_age_s,
            "snapshot_user":     snapshot_user,
            "snapshot_acc_time": snapshot_acc_time,
            # Flush
            "last_flush_age_s":  flush_age_s,
            "flush_timer_active": coordinator._session_flush_cancel is not None,
            "flush_interval_s":   60,
            # InfluxDB
            "write_age_s":       write_age_s,
            "buffer_size":       len(coordinator.failed_writes),
            "buffer_max":        100,
            "consec_failures":   consec_failures,
            # Monthly data
            "monthly_loaded":    coordinator._monthly_loaded,
        })
    except Exception as err:
        connection.send_error(msg["id"], "unknown_error", str(err))


@websocket_api.websocket_command({"type": f"{DOMAIN}/get_family_safety"})
@callback
def ws_get_family_safety(hass, connection, msg):
    """Return Microsoft Family Safety data for all configured users.

    Reads HA sensor states directly — no extra InfluxDB queries needed.
    Returns screen_time (minutes today), balance (DKK), account info,
    and pending requests count per user.
    """
    coordinator = _get_coordinator(hass)
    if not coordinator:
        connection.send_error(msg["id"], "not_ready", "Integration not ready")
        return
    try:
        entry = coordinator.config_entry
        from .const import CONF_FAMILY_SAFETY_MAPPINGS
        fs_mappings: dict = entry.data.get(CONF_FAMILY_SAFETY_MAPPINGS, {})

        result: dict = {}
        for user_id, prefix in fs_mappings.items():
            if not prefix:
                continue
            p = prefix.rstrip("_")

            def _state(suffix, _p=p):
                s = hass.states.get(f"sensor.{_p}_{suffix}")
                if s is None or s.state in ("unavailable", "unknown", "none", ""):
                    return None
                return s.state

            def _attr(suffix, attr, _p=p):
                s = hass.states.get(f"sensor.{_p}_{suffix}")
                return s.attributes.get(attr) if s else None

            st_state = _state("screen_time")
            result[user_id] = {
                "user_id":          user_id,
                "prefix":           prefix,
                "screen_time_min":  int(st_state) if st_state is not None else None,
                "screen_time_secs": _attr("screen_time", "total_seconds"),
                "screen_time_date": _attr("screen_time", "date"),
                "screen_time_fmt":  _attr("screen_time", "formatted_time"),
                "balance_dkk":      float(_state("balance")) if _state("balance") is not None else None,
                "account_name":     _state("account_info"),
                "device_count":     _attr("account_info", "device_count"),
                "app_count":        _attr("account_info", "application_count"),
                "profile_picture":  _attr("account_info", "profile_picture"),
                "pending_count":    int(_state("pending_requests")) if _state("pending_requests") is not None else None,
                "pending_requests": _attr("pending_requests", "requests") or [],
            }

        connection.send_result(msg["id"], {
            "users":    result,
            "mappings": fs_mappings,
        })
    except Exception as err:
        _LOGGER.exception("Error reading Family Safety data: %s", err)
        connection.send_error(msg["id"], "unknown_error", str(err))


@websocket_api.websocket_command(vol.All(vol.Schema({vol.Required("type"): f"{DOMAIN}/save_family_safety", vol.Optional("family_safety_mappings"): dict}, extra=vol.ALLOW_EXTRA)))
@websocket_api.async_response
async def ws_save_family_safety(hass, connection, msg):
    """Save family safety mappings separately — avoids voluptuous extra-key rejection.

    Receives the full message dict and extracts mappings manually so voluptuous
    never sees the arbitrary user-keyed dict.
    """
    coordinator = _get_coordinator(hass)
    if not coordinator:
        connection.send_error(msg["id"], "not_ready", "Integration not ready")
        return
    try:
        from .const import CONF_FAMILY_SAFETY_MAPPINGS
        # Read raw mappings directly from msg — bypasses voluptuous schema
        raw = msg.get("family_safety_mappings", {})
        if not isinstance(raw, dict):
            connection.send_error(msg["id"], "invalid_input", "family_safety_mappings must be a dict")
            return
        clean = {str(k): str(v) for k, v in raw.items() if k}
        entry = coordinator.config_entry
        new_data = {**entry.data, CONF_FAMILY_SAFETY_MAPPINGS: clean}
        hass.config_entries.async_update_entry(entry, data=new_data)
        _LOGGER.info("Family Safety mappings saved: %s", list(clean.keys()))
        connection.send_result(msg["id"], {"success": True, "mappings": clean})
    except Exception as err:
        _LOGGER.exception("Error saving Family Safety mappings: %s", err)
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
            "devices": store.get_devices(),
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
    results = data.get("results", [{}])
    series_list = results[0].get("series", []) if results else []

    all_days: list[str] = []
    user_series: dict[str, dict[str, dict]] = {}

    for s in series_list:
        user = s.get("tags", {}).get("user", "unknown")
        cols = s.get("columns", [])
        vals = s.get("values", [])

        try:
            t_idx = cols.index("time")
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
            "host":           entry.data.get("host", ""),
            "port":           entry.data.get("port", 8086),
            "database":       entry.data.get("database", ""),
            "username":       entry.data.get("username", ""),
            "user_entity":          entry.data.get("user_entity",         "sensor.flemming_gamer_satellite_loggeduser"),
            "watt_entity":          entry.data.get("watt_entity",          "sensor.gamer_pc_power_monitor_current_consumption"),
            "device_power_entity":  entry.data.get("device_power_entity", "sensor.gamer_pc_power_monitor_device_power"),
            "price_entity":         entry.data.get("price_entity",        "sensor.energi_data_service"),
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
            "user_mappings":  entry.options.get("user_mappings", coordinator.user_map),
            "tracked_users":  coordinator.tracked_users,
            "family_safety_mappings": entry.data.get("family_safety_mappings", {}),
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

        user_mappings = msg["user_mappings"]
        tracked_users = msg["tracked_users"]

        if not isinstance(user_mappings, dict) or not user_mappings:
            connection.send_error(msg["id"], "invalid_input", "user_mappings must be a non-empty dict"); return
        if not isinstance(tracked_users, list) or not tracked_users:
            connection.send_error(msg["id"], "invalid_input", "tracked_users must be a non-empty list"); return

        from .const import CONF_USER_MAPPINGS, CONF_TRACKED_USERS
        new_options = {
            **entry.options,
            CONF_USER_MAPPINGS: user_mappings,
            CONF_TRACKED_USERS: tracked_users,
        }

        new_data = dict(entry.data)
        for field in ("user_entity", "watt_entity", "device_power_entity", "price_entity"):
            if field in msg and msg[field].strip():
                new_data[field] = msg[field].strip()
        for field in ("gauge1_entity", "gauge1_label", "gauge1_max",
                      "gauge2_entity", "gauge2_label", "gauge2_max",
                      "gauge3_entity", "gauge3_label", "gauge3_max",
                      "gauge4_entity", "gauge4_label", "gauge4_max",
                      "gauge5_entity", "gauge5_label", "gauge5_max"):
            if field in msg:
                new_data[field] = msg[field].strip()

        # Family Safety mappings — validated manually, not via voluptuous
        # (voluptuous does not allow arbitrary string keys in nested dicts)
        raw_fs = msg.get("family_safety_mappings")
        if isinstance(raw_fs, dict):
            new_data["family_safety_mappings"] = {
                str(k): str(v) for k, v in raw_fs.items() if k
            }

        hass.config_entries.async_update_entry(entry, data=new_data, options=new_options)

        _LOGGER.info("Configuration saved — integration will reload")
        connection.send_result(msg["id"], {"success": True, "reload": True})

    except Exception as err:
        _LOGGER.exception("Error saving config: %s", err)
        connection.send_error(msg["id"], "unknown_error", str(err))
