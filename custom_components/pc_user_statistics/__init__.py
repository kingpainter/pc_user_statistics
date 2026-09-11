# File Name: __init__.py
# Version: 2.17.0
# Description: Main setup and coordinator for the PC User Statistics integration.
# Last Updated: September 10, 2026
#
# Changes in 2.17.0:
#   BREAKING: InfluxDB/VictoriaMetrics dependency removed entirely — the
#        add-on was deprecated in HA and no longer installable. Monthly/
#        daily totals now come from Home Assistant's own recorder long-term
#        statistics instead of an external TSDB:
#          - _async_load_monthly_data() / _async_load_daily_data(): InfluxQL
#            SUM query replaced by _async_sum_period_from_statistics(), which
#            sums the recorder's hourly "change" statistic for the monthly_
#            time/energy/cost entities over the query window. No more
#            retry/backoff — this is a local DB read, not a network call to
#            an add-on that might not be up yet.
#          - _calculate_deltas() no longer writes anywhere. apply_delta()
#            already ran unconditionally every poll before this change (only
#            the InfluxDB write itself was WRITE_THRESHOLD-gated) — removing
#            the write changes nothing about in-memory total accuracy. The
#            monthly_*/daily sensors' own state updates are what HA's
#            recorder observes to build the statistics read back above.
#          - _async_write_to_influx/_write_point_to_influx/_escape_influx_tag,
#            the failed-writes FIFO buffer, the retry/backoff machinery, the
#            consecutive-failure repair issue, and _async_verify_influxdb are
#            all deleted — no external write to retry or verify anymore.
#          - async_add_manual_entry() applies a correction directly to the
#            in-memory trackers instead of writing a tagged InfluxDB point.
#            Known limitation: a correction dated in a PAST month/day no
#            longer retroactively affects the history graph (see its
#            docstring) — HA's own long-term statistics can't be backfilled
#            for a bygone day the way a raw InfluxDB point could.
#        const.py: monthly_cost changed state_class TOTAL → TOTAL_INCREASING
#        to match monthly_time/monthly_energy (TOTAL needs an explicit
#        last_reset to reset correctly, which was never set — switched so
#        the same auto-reset-detection that already worked for the other two
#        now covers cost as well). config_flow.py's connection step and
#        helpers.validate_influxdb_config/parse_influxdb_response removed.
#        websocket.py's _query_history (history graph) migrated the same way
#        — see that file's changelog.
#
# Changes in 2.16.0:
#   REFACTOR: self.monthly/self._pending and self.daily/self._daily_pending —
#        two near-identical parallel implementations of the same bookkeeping —
#        replaced with a single PeriodTracker class (period_tracker.py), one
#        instance per period (self._monthly_tracker, self._daily_tracker).
#        No behavioral change: same floor-against-baseline logic, same
#        pending-buffer-before-load semantics, same rollover reset. Pure
#        deduplication so the next fix to this logic (the daily tracker
#        itself was born from a bug caused by this duplication) only needs
#        to be made once. self.monthly / self.daily / self._monthly_loaded /
#        self._daily_loaded remain available with identical read/write
#        semantics via thin properties, so no other file needed to change.
#
# Changes in 2.15.0:
#   NEW: Daily ("today") totals tracker — self.daily, mirroring self.monthly
#        in every way (delta accumulation, InfluxDB load with baseline floor
#        protection, periodic persistence, day-rollover reset). Added because
#        the Statistik tab's MS Family Safety comparison was silently
#        comparing MS's "screen time today" against the PC's WHOLE-MONTH
#        total (labelled "Skærmtid i dag" on both sides) — misleading more and
#        more as the month progressed. panel.js now reads `daily` instead of
#        `monthly` for that specific comparison.
#   FIX: Month AND day rollover now use Europe/Copenhagen local time
#        (LOCAL_TIMEZONE, const.py) instead of UTC. UTC rollover fired up to
#        2 hours late during CEST (UTC+2) — same class of bug as the Historik
#        tab's tz fix in websocket.py 3.5.0. The InfluxDB WHERE-clause start
#        boundaries for both monthly and daily loads are now computed from
#        local midnight, converted to UTC, instead of UTC midnight.
#
# Changes in 2.14.0:
#   NEW: Monthly baseline protection. _async_load_monthly_data() previously
#        overwrote self.monthly unconditionally with whatever InfluxDB's SUM
#        query returned — on EVERY coordinator restart/reload (HA restart,
#        or an integration reload triggered by any config save). If InfluxDB
#        was missing recent writes at that exact moment (e.g. stuck in the
#        RAM-only failed_writes buffer during an outage), the fresh sum could
#        be LOWER than what had already been tracked and shown — silently
#        erasing real, already-counted playtime/energy/cost. Confirmed in
#        production: recorder's own history for sensor.statistics_sebastian_duration
#        showed the raw monthly-seconds value drop mid-month (no month rollover)
#        at least 4 times in July, losing ~10.8 hours of tracked time total.
#        Fix: a monthly baseline (self._persisted_monthly_baseline) is now
#        persisted to the config store (store.py 2.11.0) on every periodic
#        flush, after every successful InfluxDB load, and at shutdown.
#        _async_load_monthly_data() now takes max(InfluxDB sum, baseline) per
#        user/metric — it can only go up, never down — and falls back to the
#        baseline entirely (instead of resetting to 0) if all retries fail.
#        The baseline is correctly cleared at genuine month rollover so a new
#        month isn't inflated by last month's numbers.
#        MAX_RETRY_ATTEMPTS raised 3 → 20 (const.py) so individual write
#        points aren't silently dropped within minutes of an InfluxDB outage.
#
# Changes in 2.13.0:
#   NEW: Robust price fallback. _get_price() previously defaulted to 0.0
#        DKK/kWh whenever the price sensor was unavailable/unknown, silently
#        zeroing cost for that period while time/energy kept accumulating
#        correctly. It now caches the last known valid price and falls back
#        to that instead of 0.0 — only 0.0 if no valid price has ever been
#        read (e.g. right after HA startup). Fallback usage is counted
#        (_price_fallback_count, reset monthly) and rate-limited-logged
#        (PRICE_FALLBACK_LOG_INTERVAL) so a sensor outage is visible instead
#        of silent. New fields exposed via _get_data()/ws_get_health:
#        price_fallback_count, last_valid_price, price_entity_ok.
#        The fallback cache is also persisted in the session snapshot
#        (store.py 2.10.0) so it survives a HA restart.
#
# Changes in 2.12.1:
#   FIX 1: diagnostics.py uses entry.runtime_data (done in diagnostics.py)
#   FIX 2: system_health.py uses entry.runtime_data (done in system_health.py)
#   FIX 3: _idle_since comment restored in __init__
#   FIX 4: last_power reset to 0.0 on logout in _handle_user_change
#   FIX 5: _escape_influx_tag() helper — escapes commas, spaces, equals in
#        user tag values for InfluxDB line protocol correctness
#   FIX 6: store.py async_save_rule/async_save_devices try/except (done in store.py)
#   FIX 7: asyncio.Lock guard in _async_update_data prevents concurrent
#        execution if a poll takes longer than the 60s update interval
#
# Changes in 2.12.0:
#   FIX 3: _retry_failed_writes() now has exponential backoff — after 3
#        consecutive retry-poll failures, retries are skipped for an
#        increasing number of polls (2, 4, 8 … capped at 32) so a
#        long-running InfluxDB outage doesn't hammer the server every 60s.
#        New fields: _retry_skip_count, _retry_skip_remaining.
#   FIX 4: _async_periodic_flush() now sets _unloaded guard check AFTER
#        the async_flush_session() call, not only at entry. Prevents a
#        race where async_shutdown() runs concurrently with an in-progress
#        flush task — the flush now completes cleanly before reschedule.
#   FIX 5: _read_ms_screen_time() call deduplicated in _async_write_to_influx
#        — previously called once on success path and once on failure path
#        with identical code. Now called once before the branch.
#   FIX 6 (websocket): _query_history reuses coordinator._http_session
#        instead of opening a new aiohttp.ClientSession per request, and
#        uses a 5s timeout matching the coordinator default.
#
# Changes in 2.11.0:
#   NEW: async_add_manual_entry(user, timestamp_ns, time_delta, energy_delta,
#        cost_delta) — writes a one-off InfluxDB point tagged source=manual
#        for ad-hoc corrections when a session was lost (e.g. files were
#        overwritten mid-session). Reloads monthly totals immediately after
#        a successful write. Exposed via websocket.ws_add_manual_entry and a
#        new "Manuel korrektion" form on the panel's Admin tab.
#
# Changes in 2.10.0:
#   FIX 1A: entry.runtime_data = coordinator now set in async_setup_entry,
#        right after first refresh. Used by websocket._get_coordinator()
#        (Fix 1B) instead of duck-typing on hass.data[DOMAIN].
#   FIX 2: _schedule_session_flush() now has a liveness guard — if the
#        previous periodic flush is >90s overdue while a session is active,
#        a warning is logged. New field _last_flush_monotonic tracks this.
#   FIX 4: Defensive assertion after _normalize_user_map() in __init__ —
#        any remaining non-string user_map values are logged as an error
#        and dropped, instead of silently being re-normalized later in
#        _handle_user_change().
#
# Changes in 2.9.0:
#   NEW: Microsoft Family Safety gap-fill on HA restart.
#        At shutdown, MS screen_time (minutes) and date are saved to the session
#        snapshot. At startup, _async_restore_session() reads the current MS
#        screen_time and adds the delta to acc_time — recovering time lost while
#        HA was down. Only applies to users with a Family Safety mapping.
#        Capped at 4 hours delta to guard against sensor anomalies.
#        New helper: _read_ms_screen_time(user) — reads sensor.{prefix}_screen_time.
#
# Changes in 2.8.0:
#   NEW: Periodic session flush every 60s via async_call_later, independent of
#        InfluxDB writes. Fixes data loss when InfluxDB is down across multiple
#        consecutive HA restarts — session state is now always persisted to disk
#        regardless of InfluxDB availability.
#   NEW: ws_get_health WebSocket command exposes session snapshot age, flush
#        timestamp, and buffer state for the health widget in the panel Admin tab.
#   NEW: store.py split into two storage keys: pc_user_statistics.config for
#        notification rules/devices, and pc_user_statistics.session for session
#        state. Isolates corruption between the two concerns.
#
# Changes in 2.7.4:
#   FIX: last_write_time initialised to 0.0 instead of time.time().
#        system_health.py uses last_write_time > 0 to detect whether a real
#        write has occurred. Initialising to time.time() made health always
#        show a recent (fake) write time on startup, hiding the "aldrig" state.
#        Now correctly shows "aldrig" until the first successful InfluxDB write.
#
# Changes in 2.7.3:
#   FIX 1: Session snapshot now flushed to disk on EVERY successful InfluxDB write.
#           Previously save_session_in_memory() was called but async_flush_session()
#           was not — the snapshot only reached disk if a notification rule fired
#           (notification_manager.async_flush() is conditional on any_sent).
#           In practice: no notifications = session never persisted = data loss on restart.
#
#   FIX 2: Removed force_write=True from coordinator poll (_async_update_data).
#           force_write bypassed the WRITE_THRESHOLD guard. Combined with the
#           state-change handler also able to trigger writes, this caused double
#           writes within the same 60s window → double-counting in InfluxDB.
#           Coordinator poll now uses force_write=False (default). The 60s
#           WRITE_THRESHOLD in _calculate_deltas is the single source of truth.
#
# Changes in 2.7.2:
#   FIX: Session snapshot now saved immediately on user login.
#        Previously the first snapshot was written ~60s after login
#        (on the first InfluxDB write). If HA restarted within those
#        60s, current_user was not recoverable. One extra disk write
#        at login closes this gap — max data loss is now ~0s at login.
#
# Changes in 2.7.1:
#   FIX 1: Session snapshot now saved to disk even when InfluxDB write fails.
#           Previously, if InfluxDB was unreachable, no snapshot was written
#           and acc_time was lost on HA restart. Now uses async_flush_session()
#           for an immediate disk write in the failure path.
#
#   FIX 2: _async_restore_session() now receives the store instance directly
#           from async_setup_entry instead of fetching it from hass.data via
#           asyncio.sleep(0). Eliminates timing fragility at startup.
#   NEW: Session persistence — survives HA restart mid-session.
#        Session state (current_user, acc_time, acc_energy, acc_cost, last_time)
#        is saved to disk on every successful InfluxDB write (~every 60s) and
#        restored at HA startup. Max data loss on HA restart: ~60s.
#        New method: _async_restore_session()
#        Logout clears the snapshot so stale sessions are never restored.
#
# Changes in 2.6.2:
#   FIX: Removed entry.add_update_listener(_async_options_updated).
#        The listener triggered an immediate async_reload() whenever options were
#        updated, which unloaded the integration while ws_save_config() was still
#        waiting to send its WebSocket response. This caused a silent crash:
#        the panel froze, data was not saved, and only a full HA restart helped.
#
#        Integration reload is now triggered exclusively by ws_save_config() via
#        hass.async_create_task(_do_reload()), which runs AFTER send_result() has
#        been delivered to the browser. This guarantees the WS round-trip completes
#        before the coordinator is torn down.

from datetime import datetime, timedelta, timezone
import asyncio
import logging
import time
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry, ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers import entity_registry as er
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    USER_ENTITY,
    WATT_ENTITY,
    DEVICE_POWER_ENTITY,
    PRICE_ENTITY,
    UPDATE_INTERVAL,
    PRICE_FALLBACK_LOG_INTERVAL,
    LOCAL_TIMEZONE,
    CONF_USER_MAPPINGS,
    CONF_TRACKED_USERS,
    DEFAULT_USER_MAP,
    DEFAULT_USERS,
)
from .helpers import safe_float_from_state
from .store import NotificationStore
from .notification_manager import NotificationManager
from .period_tracker import PeriodTracker

# Sensor keys (see const.SENSOR_CONFIGS) whose HA long-term statistics back
# _async_sum_period_from_statistics() — both the monthly and daily totals,
# and the history graph, read from these same three entities per user.
_PERIOD_METRIC_SENSOR_KEYS: dict[str, str] = {
    "time": "monthly_time", "energy": "monthly_energy", "cost": "monthly_cost",
}

_LOGGER = logging.getLogger(__name__)


def _normalize_user_map(raw: dict) -> dict[str, str]:
    """
    Normalize user_map values to plain strings.

    The config UI (ws_save_config) may store values as dicts when an HA user
    is linked, e.g. {'user_id': 'lukas', 'ha_user': 'da88c1c...'}.
    The coordinator only needs the user_id string for session tracking.
    """
    normalized: dict[str, str] = {}
    for sensor_state, value in raw.items():
        if isinstance(value, dict):
            user_id = value.get("user_id", "")
            if user_id:
                normalized[sensor_state] = str(user_id).lower()
            else:
                _LOGGER.warning(
                    "user_map entry '%s' is a dict without 'user_id', skipping: %s",
                    sensor_state, value,
                )
        elif isinstance(value, str) and value:
            normalized[sensor_state] = value.lower()
        else:
            _LOGGER.warning(
                "user_map entry '%s' has unexpected value type %s, skipping: %s",
                sensor_state, type(value).__name__, value,
            )
    return normalized


def _assert_string_user_map(user_map: dict[str, str]) -> dict[str, str]:
    """Fix 4: defensive last-line check that user_map values are plain strings.

    _normalize_user_map() should already guarantee this, but fails loudly and
    early if it doesn't — downstream code (_handle_user_change) assumes plain
    strings and would otherwise have to re-implement this normalization on the
    fly for dict values that slipped through.

    Returns user_map unchanged if all values are strings, otherwise logs an
    error and returns a copy with the offending entries removed.
    """
    non_strings = {k: v for k, v in user_map.items() if not isinstance(v, str)}
    if not non_strings:
        return user_map
    _LOGGER.error(
        "user_map contains non-string values after normalization — "
        "these entries will be ignored: %s", non_strings,
    )
    return {k: v for k, v in user_map.items() if isinstance(v, str)}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PC User Statistics from a config entry."""
    _LOGGER.info("Setting up PC User Statistics integration (entry: %s)", entry.entry_id)

    try:
        coordinator = PCStatisticsCoordinator(hass, entry)
        store = NotificationStore(hass)

        # v2.17.0 — no more InfluxDB connectivity to verify; just load the
        # persistent store.
        await store.async_load()

        # v2.14.0 — wire up direct store reference and restore the monthly
        # baseline floor BEFORE _async_load_monthly_data() ever runs, so the
        # very first load already has something to protect against.
        coordinator._store = store
        coordinator._persisted_monthly_baseline = store.get_monthly_baseline()
        coordinator._persisted_daily_baseline = store.get_daily_baseline()

        await coordinator.async_config_entry_first_refresh()

        # Fix 1A: expose coordinator via entry.runtime_data — the modern HA
        # pattern. websocket._get_coordinator() reads this directly instead of
        # iterating hass.data[DOMAIN] and duck-typing on tracked_users.
        entry.runtime_data = coordinator

        notification_manager = NotificationManager(hass, store)

        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
        hass.data[DOMAIN]["store"] = store
        hass.data[DOMAIN]["notification_manager"] = notification_manager

        await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

        entry.async_on_unload(
            async_track_state_change_event(
                hass,
                [coordinator._user_entity, coordinator._watt_entity],
                coordinator._handle_state_change,
            )
        )

        # Restore persisted session — called here with store directly to avoid
        # timing dependency on hass.data population order.
        await coordinator._async_restore_session(store)

        # Start periodic session flush — ensures session reaches disk every 60s.
        coordinator._schedule_session_flush()

        # v2.14.0 — monthly data load is scheduled here (not in __init__) so it
        # only runs after coordinator._store and _persisted_monthly_baseline are
        # wired up above. Scheduling it from __init__ would race against that.
        hass.async_create_task(coordinator._async_load_monthly_data())
        hass.async_create_task(coordinator._async_load_daily_data())

        # Read the current user sensor state at startup.
        # async_track_state_change_event only fires on *future* changes — if HA restarts
        # while a user is already logged in, the sensor never fires again and current_user
        # stays None, silently discarding all playtime until the next login event.
        initial_user_state = hass.states.get(coordinator._user_entity)
        if initial_user_state and initial_user_state.state not in (
            "unavailable", "unknown", "none", "",
        ):
            user_key = initial_user_state.state.lower()
            raw_mapped = coordinator.user_map.get(user_key)
            if isinstance(raw_mapped, dict):
                initial_user = raw_mapped.get("user_id") or None
            elif isinstance(raw_mapped, str) and raw_mapped:
                initial_user = raw_mapped
            else:
                initial_user = None
            if initial_user:
                coordinator.current_user = initial_user
                coordinator.last_time = time.time()
                coordinator.last_power = coordinator._get_power()
                _LOGGER.info(
                    "Startup: '%s' already logged in — resuming session tracking",
                    initial_user,
                )

        from .websocket import async_register_websocket_commands
        from .panel import async_register_panel
        async_register_websocket_commands(hass)
        await async_register_panel(hass)

        _LOGGER.info("PC User Statistics setup completed successfully")
        return True

    except (ConfigEntryAuthFailed, ConfigEntryNotReady):
        raise
    except Exception as err:
        _LOGGER.exception("Unexpected error setting up PC User Statistics: %s", err)
        raise ConfigEntryNotReady(f"Unexpected setup error: {err}") from err


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading PC User Statistics integration (entry: %s)", entry.entry_id)

    try:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
        if unload_ok:
            coordinator: PCStatisticsCoordinator = hass.data[DOMAIN].get(entry.entry_id)
            if coordinator:
                await coordinator.async_shutdown()

            from .panel import async_unregister_panel, async_unregister_cards_resource
            async_unregister_panel(hass)
            await async_unregister_cards_resource(hass)

            # Remove all DOMAIN keys — prevents stale store/notification_manager
            # references leaking into the next reload cycle
            domain_data = hass.data.get(DOMAIN, {})
            domain_data.pop(entry.entry_id, None)
            domain_data.pop("store", None)
            domain_data.pop("notification_manager", None)

            _LOGGER.info("PC User Statistics unloaded successfully")
        return unload_ok

    except Exception as err:
        _LOGGER.exception("Failed to unload PC User Statistics integration: %s", err)
        return False


class PCStatisticsCoordinator(DataUpdateCoordinator):
    """Coordinator for fetching and managing PC statistics data."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.config_entry = config_entry
        self.config = config_entry.data

        # ── User configuration ─────────────────────────────────────────────
        raw_map = config_entry.options.get(CONF_USER_MAPPINGS, dict(DEFAULT_USER_MAP))
        self.user_map: dict[str, str] = _assert_string_user_map(_normalize_user_map(raw_map))

        self.tracked_users: list[str] = config_entry.options.get(
            CONF_TRACKED_USERS, list(DEFAULT_USERS)
        )
        _LOGGER.info(
            "User configuration loaded — tracked: %s, mappings: %s",
            self.tracked_users, self.user_map,
        )

        # ── Session tracking ───────────────────────────────────────────────
        self.current_user: str | None = None
        self.acc_time: float = 0.0
        self.acc_energy: float = 0.0
        self.acc_cost: float = 0.0

        # ── Monthly totals (in-memory, loaded from InfluxDB at startup) ────
        # IMPORTANT: Do NOT accumulate deltas directly into self.monthly until
        # _async_load_monthly_data() completes. Until then, all deltas go into
        # self._pending, which is merged into self.monthly after the InfluxDB
        # load. This prevents double-counting: if a delta is written to InfluxDB
        # before the load completes, it would appear in both the InfluxDB SUM
        # and self.monthly if we accumulated there directly.
        # v2.16.0 — monthly and daily bookkeeping (totals / pending-before-load
        # buffer / loaded flag / baseline-floor merge) now live in a shared
        # PeriodTracker (period_tracker.py) instead of two hand-duplicated sets
        # of attributes. self.monthly / self.daily / self._monthly_loaded /
        # self._daily_loaded below are thin properties delegating to these —
        # see the property definitions after __init__ for details.
        self._monthly_tracker = PeriodTracker("month", self.tracked_users)
        self._daily_tracker = PeriodTracker("day", self.tracked_users)

        # ── Timing ────────────────────────────────────────────────────────
        self.last_time: float = time.time()
        self.last_power: float = 0.0
        # v2.15.0 — month/day rollover tracked in LOCAL time (Europe/Copenhagen),
        # not UTC. UTC rollover fired up to 2 hours late during CEST (UTC+2).
        _now_local = datetime.now(ZoneInfo(LOCAL_TIMEZONE))
        self.last_month: int = _now_local.month
        self.last_day = _now_local.date()
        # FIX v2.7.4: initialised to 0.0 (not time.time()) so system_health
        # correctly shows "aldrig" until the first delta is actually applied.
        # v2.17.0: no longer gates an InfluxDB write — just a "last update"
        # timestamp for ws_get_system/ws_get_health, set on every applied delta.
        self.last_write_time: float = 0.0

        # ── Cached entity IDs — read once at init, not on every state lookup ──
        self._user_entity: str   = config_entry.data.get("user_entity",          USER_ENTITY)
        self._watt_entity: str   = config_entry.data.get("watt_entity",          WATT_ENTITY)
        self._device_entity: str = config_entry.data.get("device_power_entity",  DEVICE_POWER_ENTITY)
        self._price_entity: str  = config_entry.data.get("price_entity",         PRICE_ENTITY)

        # Guard: prevents background tasks from running after unload
        self._unloaded: bool = False

        # Idle tracking: set when user logs out, cleared when user logs in.
        # Used by idle_pc notification rule as the correct idle duration source.
        self._idle_since: float | None = None

        # Timestamp of last session flush to disk (independent of InfluxDB writes)
        self._last_session_flush: float = 0.0
        # Monotonic timestamp of last flush — used by the Fix 2 liveness guard.
        # (monotonic, unlike time.time(), can't jump backwards on clock changes)
        self._last_flush_monotonic: float = 0.0
        # Cancel callback for the periodic session flush timer
        self._session_flush_cancel = None

        # Fix 7 — concurrent execution guard: DataUpdateCoordinator schedules
        # _async_update_data on a fixed interval. If a call takes longer than
        # the interval (e.g. a slow statistics query), a second call can start
        # before the first finishes. The lock prevents overlapping runs.
        self._update_lock: asyncio.Lock = asyncio.Lock()

        # ── Price fallback cache (v2.13.0) ──────────────────────────────────
        # _get_price() falls back to _last_valid_price instead of 0.0 when the
        # price sensor is unavailable/unknown. _price_fallback_count is reset
        # every month rollover; _last_price_warning_time rate-limits the log
        # warning so a prolonged sensor outage doesn't spam the log every 60s.
        self._last_valid_price: float = 0.0
        self._last_valid_price_time: float = 0.0
        self._price_fallback_count: int = 0
        self._last_price_warning_time: float = 0.0

        # ── Monthly baseline protection (v2.14.0) ─────────────────────
        # Direct reference to the NotificationStore, set by async_setup_entry
        # right after both are created. Used to persist/restore a "floor" for
        # monthly totals so _async_load_monthly_data() can never show LESS
        # than what was already tracked (e.g. after a restart during an
        # InfluxDB outage that left recent writes stuck in the RAM buffer).
        self._store = None
        self._persisted_monthly_baseline: dict[str, dict[str, float]] = {}
        # Same protection for the daily tracker (v2.15.0)
        self._persisted_daily_baseline: dict[str, dict[str, float]] = {}

        # NOTE: _async_load_monthly_data() is intentionally NOT scheduled here.
        # It's scheduled explicitly by async_setup_entry, AFTER _store and
        # _persisted_monthly_baseline are wired up above — scheduling it here
        # (before either exists) would race against that wiring and the very
        # first load would run with no baseline to protect against.

        _LOGGER.debug("PCStatisticsCoordinator initialized (entry: %s)", config_entry.entry_id)

    # ── PeriodTracker compatibility properties (v2.16.0) ───────────────────
    # Thin delegation so every other file (websocket.py, sensor.py,
    # diagnostics.py, system_health.py) and the rest of this file can keep
    # reading/writing self.monthly, self.daily, self._monthly_loaded,
    # self._daily_loaded exactly as before the PeriodTracker refactor.

    @property
    def monthly(self) -> dict[str, dict[str, float]]:
        return self._monthly_tracker.totals

    @property
    def daily(self) -> dict[str, dict[str, float]]:
        return self._daily_tracker.totals

    @property
    def _monthly_loaded(self) -> bool:
        return self._monthly_tracker.loaded

    @_monthly_loaded.setter
    def _monthly_loaded(self, value: bool) -> None:
        self._monthly_tracker.loaded = value

    @property
    def _daily_loaded(self) -> bool:
        return self._daily_tracker.loaded

    @_daily_loaded.setter
    def _daily_loaded(self, value: bool) -> None:
        self._daily_tracker.loaded = value

    def _read_ms_screen_time(self, user: str) -> tuple[int | None, str | None]:
        """Read Microsoft Family Safety screen_time for a user from HA states.

        Returns (minutes: int | None, date: str | None).
        Returns (None, None) if no Family Safety mapping exists for the user
        or if the sensor is unavailable.
        """
        from .const import CONF_FAMILY_SAFETY_MAPPINGS
        fs_mappings: dict = self.config_entry.data.get(CONF_FAMILY_SAFETY_MAPPINGS, {})
        prefix = fs_mappings.get(user)
        if not prefix:
            return None, None
        p = prefix.rstrip("_")
        state = self.hass.states.get(f"sensor.{p}_screen_time")
        if state is None or state.state in ("unavailable", "unknown", "none", ""):
            return None, None
        try:
            minutes = int(state.state)
            date = state.attributes.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            return minutes, str(date)
        except (ValueError, TypeError):
            return None, None

    async def async_shutdown(self) -> None:
        """Flush pending state to disk. Called on integration unload."""
        self._unloaded = True  # Stop any pending background tasks
        # Cancel the periodic session flush timer so it does not fire after unload
        if self._session_flush_cancel is not None:
            self._session_flush_cancel()
            self._session_flush_cancel = None

        # v2.14.0 — persist monthly baseline on shutdown too, independent of
        # whether a session is active, so a restart right after shutdown has
        # the freshest possible floor to protect against.
        if self._store is not None and self._monthly_loaded:
            self._store.save_monthly_baseline_in_memory(self.monthly)
            await self._store.async_flush_monthly_baseline()
        if self._store is not None and self._daily_loaded:
            self._store.save_daily_baseline_in_memory(self.daily)
            await self._store.async_flush_daily_baseline()

        # Snapshot Microsoft screen_time before shutdown so _async_restore_session
        # can compute the gap delta on next startup.
        if self.current_user:
            _store = self.hass.data.get(DOMAIN, {}).get("store")
            if _store and _store.get_session():
                ms_min, ms_date = self._read_ms_screen_time(self.current_user)
                if ms_min is not None:
                    _store.save_session_in_memory(
                        self.current_user,
                        self.acc_time,
                        self.acc_energy,
                        self.acc_cost,
                        time.time(),
                        ms_screen_time=ms_min,
                        ms_screen_time_date=ms_date,
                        last_valid_price=self._last_valid_price,
                        last_valid_price_time=self._last_valid_price_time,
                    )
                    # await directly — async_create_task is unreliable during shutdown
                    await _store.async_flush_session()
                    _LOGGER.debug(
                        "Shutdown: saved MS screen_time=%d min (%s) for gap-fill on next startup",
                        ms_min, ms_date,
                    )

    def _schedule_session_flush(self) -> None:
        """Schedule a periodic session flush every 60s.

        This guarantees that session state reaches disk on its own schedule,
        independent of the coordinator's poll cycle.

        Fix 2 — liveness guard: if the previous flush is significantly overdue
        while a session is active, log a warning. A crashed/cancelled timer
        would otherwise fail silently and cause quiet session data loss.
        """
        if self._unloaded:
            return

        now_mono = time.monotonic()
        if (
            self._last_flush_monotonic > 0
            and (now_mono - self._last_flush_monotonic) > 90
            and self.current_user is not None
        ):
            _LOGGER.warning(
                "Session flush timer overdue (%.0fs since last flush) — rescheduling",
                now_mono - self._last_flush_monotonic,
            )

        if self._session_flush_cancel is not None:
            self._session_flush_cancel()

        @callback
        def _flush_callback(now):
            """Fire async session flush and reschedule."""
            if self._unloaded:
                return
            self.hass.async_create_task(self._async_periodic_flush())

        self._session_flush_cancel = async_call_later(self.hass, 60, _flush_callback)

    async def _async_periodic_flush(self) -> None:
        """Flush session snapshot and monthly baseline to disk, reschedule next flush.

        Fix 4 — shutdown race guard: _unloaded is checked both at entry and
        after the async_flush_session() call. This prevents a race where
        async_shutdown() cancels the timer but a flush task is already
        running — the flush completes cleanly, then reschedule is skipped.
        """
        if self._unloaded:
            return

        # v2.14.0 — persist the monthly baseline every flush cycle, regardless
        # of whether a session is currently active. This is what lets a future
        # restart/reload know the last known-good totals instead of trusting
        # a fresh InfluxDB sum blindly (see _async_load_monthly_data()).
        if self._store is not None and self._monthly_loaded:
            self._store.save_monthly_baseline_in_memory(self.monthly)
            await self._store.async_flush_monthly_baseline()
        if self._store is not None and self._daily_loaded:
            self._store.save_daily_baseline_in_memory(self.daily)
            await self._store.async_flush_daily_baseline()

        if not self.current_user:
            # Reschedule even if no active user — ensures we pick up next login
            self._schedule_session_flush()
            return
        _store = self.hass.data.get(DOMAIN, {}).get("store")
        if _store:
            ms_min, ms_date = self._read_ms_screen_time(self.current_user)
            _store.save_session_in_memory(
                self.current_user,
                self.acc_time,
                self.acc_energy,
                self.acc_cost,
                time.time(),
                ms_screen_time=ms_min,
                ms_screen_time_date=ms_date,
                last_valid_price=self._last_valid_price,
                last_valid_price_time=self._last_valid_price_time,
            )
            await _store.async_flush_session()
            self._last_session_flush = time.time()
            self._last_flush_monotonic = time.monotonic()
            _LOGGER.debug(
                "Periodic session flush — user='%s' acc_time=%.0fs ms_screen_time=%s",
                self.current_user, self.acc_time, ms_min,
            )
        # Guard: if shutdown occurred during the flush above, do not reschedule
        if not self._unloaded:
            self._schedule_session_flush()

    # ── Home Assistant native statistics helpers (v2.17.0) ──────────────────
    # Replaces the old InfluxDB SUM query. HA's recorder already builds
    # long-term statistics for the monthly_time/monthly_energy/monthly_cost
    # entities (all state_class total_increasing as of v2.17.0 — monthly_cost
    # was `total`, which needs an explicit last_reset to reset correctly at
    # rollover; switched to total_increasing so the same auto-reset-detection
    # that already worked for time/energy now covers cost too).
    #
    # "Daily" reuses the exact same three entities — restricting the query
    # window to [today, now] gives today's own delta, exactly like
    # restricting it to [month_start, now] gives the month's delta. No
    # separate daily_* entities are needed.
    #
    # No retry/backoff needed anymore: this is a local recorder DB read, not
    # a network call to an add-on that might not be up yet at HA startup.

    def _entity_id_for(self, user: str, sensor_key: str) -> str | None:
        """Resolve a tracked entity_id via the entity registry.

        Looks up by unique_id (same scheme sensor.py uses:
        f"{entry_id}_{user}_{sensor_key}") rather than reconstructing the
        has_entity_name-derived entity_id string, which isn't guaranteed
        stable. Returns None only on a brand new install, before the sensor
        platform has ever registered the entity.
        """
        return er.async_get(self.hass).async_get_entity_id(
            "sensor", DOMAIN, f"{self.config_entry.entry_id}_{user}_{sensor_key}"
        )

    async def _async_sum_period_from_statistics(
        self, period_start_local: datetime,
    ) -> dict[str, dict[str, float]]:
        """Sum each tracked user's time/energy/cost change since period_start_local.

        1:1 replacement for the old `SELECT SUM(delta) WHERE time >= start`
        InfluxDB query — sums the recorder's hourly "change" statistic (the
        delta within that hour) for each user's monthly_time/monthly_energy/
        monthly_cost entity, over every hour bucket from period_start_local
        to now.
        """
        start = period_start_local.astimezone(timezone.utc)
        end = dt_util.utcnow()
        stats_engine = get_instance(self.hass)

        raw: dict[str, dict[str, float]] = {
            user: {"time": 0.0, "energy": 0.0, "cost": 0.0} for user in self.tracked_users
        }
        for user in self.tracked_users:
            for key, sensor_key in _PERIOD_METRIC_SENSOR_KEYS.items():
                entity_id = self._entity_id_for(user, sensor_key)
                if entity_id is None:
                    continue
                stats = await stats_engine.async_add_executor_job(
                    statistics_during_period,
                    self.hass, start, end, {entity_id}, "hour", None, {"change"},
                )
                raw[user][key] = sum(
                    (row.get("change") or 0.0) for row in stats.get(entity_id, [])
                )
        return raw

    async def _async_load_monthly_data(self) -> None:
        """Load this month's per-user totals from HA's own long-term statistics.

        v2.14.0: the freshly-loaded sum is never allowed to result in a LOWER
        total than self._persisted_monthly_baseline (loaded from disk at
        startup, updated on every periodic flush). This protects against
        silently erasing already-tracked time/energy/cost if the statistics
        read is missing the very latest state changes at the exact moment a
        restart or integration reload triggers this reload.
        """
        now_local = datetime.now(ZoneInfo(LOCAL_TIMEZONE))
        month_start_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        try:
            new_monthly_raw = await self._async_sum_period_from_statistics(month_start_local)

            # v2.14.0 floor + pending-merge, v2.16.0 delegated to PeriodTracker:
            # never let the fresh sum show less than the last known-good
            # baseline, and fold in any deltas accumulated before load completed.
            baseline = self._persisted_monthly_baseline or {}
            self._monthly_tracker.load_from_influx(new_monthly_raw, baseline)
            _LOGGER.info(
                "Monthly data loaded from HA statistics: %s",
                {u: {k: round(v, 2) for k, v in vals.items()} for u, vals in self.monthly.items()},
            )

            # Persist the freshly-reconciled totals as the new baseline right
            # away, so an immediate follow-up restart has the freshest floor.
            if self._store is not None:
                self._store.save_monthly_baseline_in_memory(self.monthly)
                await self._store.async_flush_monthly_baseline()

        except Exception as err:
            baseline = self._persisted_monthly_baseline or {}
            _LOGGER.exception(
                "Failed to load monthly data from HA statistics: %s. "
                "Falling back to last known baseline instead of resetting to 0: %s",
                err,
                {u: {k: round(v, 2) for k, v in vals.items()} for u, vals in baseline.items()} or "none available",
            )
            self._monthly_tracker.load_fallback(baseline)

    async def _async_load_daily_data(self) -> None:
        """Load today's per-user totals — see _async_load_monthly_data().

        Exact mirror of _async_load_monthly_data() — same baseline-floor
        protection via self._persisted_daily_baseline, same fallback-to-
        baseline behaviour on error. Window is local calendar "today" instead
        of "this month".
        """
        now_local = datetime.now(ZoneInfo(LOCAL_TIMEZONE))
        day_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

        try:
            new_daily_raw = await self._async_sum_period_from_statistics(day_start_local)

            # v2.16.0 — floor + pending-merge delegated to PeriodTracker (see
            # _async_load_monthly_data for the equivalent monthly comment).
            baseline = self._persisted_daily_baseline or {}
            self._daily_tracker.load_from_influx(new_daily_raw, baseline)
            _LOGGER.info(
                "Daily data loaded from HA statistics: %s",
                {u: {k: round(v, 2) for k, v in vals.items()} for u, vals in self.daily.items()},
            )

            if self._store is not None:
                self._store.save_daily_baseline_in_memory(self.daily)
                await self._store.async_flush_daily_baseline()

        except Exception as err:
            baseline = self._persisted_daily_baseline or {}
            _LOGGER.exception(
                "Failed to load daily data from HA statistics: %s. "
                "Falling back to last known baseline instead of resetting to 0.",
                err,
            )
            self._daily_tracker.load_fallback(baseline)

    async def _async_restore_session(self, store: "NotificationStore") -> None:
        """Restore in-progress session from persistent store after HA restart."""
        if not store:
            _LOGGER.debug("Session restore: store not available")
            return

        snapshot = store.get_session()
        if not snapshot:
            _LOGGER.debug("Session restore: no snapshot found")
            return

        saved_user: str | None = snapshot.get("current_user")
        saved_at: float = snapshot.get("saved_at", 0.0)
        now = time.time()
        age = now - saved_at

        if age > 4 * 3600:
            _LOGGER.info(
                "Session restore: snapshot %.0f min old — too stale, discarding",
                age / 60,
            )
            await store.async_clear_session()
            return

        if saved_user and saved_user not in self.tracked_users:
            _LOGGER.warning(
                "Session restore: user '%s' not in tracked_users — discarding",
                saved_user,
            )
            await store.async_clear_session()
            return

        try:
            sensor_state = self.hass.states.get(self._user_entity)
            if sensor_state and sensor_state.state not in ("unavailable", "unknown", "none", ""):
                live_key = sensor_state.state.lower()
                live_user = self.user_map.get(live_key)
                if live_user and live_user != saved_user:
                    _LOGGER.info(
                        "Session restore: live user '%s' ≠ snapshot user '%s' — discarding",
                        live_user, saved_user,
                    )
                    await store.async_clear_session()
                    return
        except Exception as err:
            _LOGGER.warning("Session restore: could not read user sensor: %s", err)

        self.current_user = saved_user
        self.acc_time     = snapshot.get("acc_time",   0.0)
        self.acc_energy   = snapshot.get("acc_energy", 0.0)
        self.acc_cost     = snapshot.get("acc_cost",   0.0)
        self.last_time       = now
        self.last_write_time = now

        # ── Microsoft Family Safety gap-fill ──────────────────────────────
        # If we have a MS screen_time reading from shutdown, compare it with
        # the current MS screen_time. The delta is time that passed while HA
        # was down — add it to acc_time so the gap is recovered.
        saved_ms_min: int | None  = snapshot.get("ms_screen_time")
        saved_ms_date: str | None = snapshot.get("ms_screen_time_date")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if saved_ms_min is not None and saved_ms_date == today and saved_user:
            current_ms_min, current_ms_date = self._read_ms_screen_time(saved_user)
            if current_ms_min is not None and current_ms_date == today:
                delta_min = current_ms_min - saved_ms_min
                if 0 < delta_min <= 240:  # sanity cap: max 4 hours gap
                    delta_s = float(delta_min * 60)
                    self.acc_time += delta_s
                    _LOGGER.info(
                        "MS gap-fill for '%s': +%d min (MS was %d → now %d) — acc_time now %.0fs",
                        saved_user, delta_min, saved_ms_min, current_ms_min, self.acc_time,
                    )
                elif delta_min > 240:
                    _LOGGER.warning(
                        "MS gap-fill for '%s': delta %d min exceeds 4h cap — skipping",
                        saved_user, delta_min,
                    )
                else:
                    _LOGGER.debug(
                        "MS gap-fill for '%s': delta %d min (≤0) — nothing to add",
                        saved_user, delta_min,
                    )
            else:
                _LOGGER.debug(
                    "MS gap-fill for '%s': current MS data unavailable or date mismatch — skipping",
                    saved_user,
                )
        else:
            _LOGGER.debug(
                "MS gap-fill: no saved MS data, or date mismatch (saved=%s, today=%s) — skipping",
                saved_ms_date, today,
            )

        # ── Price fallback cache restore (v2.13.0) ───────────────────
        # Seed _last_valid_price from the snapshot so _get_price() has a sane
        # fallback available immediately after restart, before the price sensor
        # has reported for the first time in this session. Capped at 6 hours —
        # older than that, a stale cached price is more likely to be wrong than
        # useful, so we let it start fresh (0.0) instead.
        saved_price = snapshot.get("last_valid_price")
        saved_price_time = snapshot.get("last_valid_price_time")
        if saved_price is not None and saved_price_time and (now - saved_price_time) < 6 * 3600:
            self._last_valid_price = float(saved_price)
            self._last_valid_price_time = float(saved_price_time)
            _LOGGER.debug(
                "Restored price fallback cache: %.2f kr/kWh (%.0fs old)",
                self._last_valid_price, now - saved_price_time,
            )

        _LOGGER.info(
            "Session restored after HA restart — user='%s' acc_time=%.0fs "
            "acc_energy=%.4fkWh acc_cost=%.4fDKK (snapshot age %.0fs)",
            self.current_user, self.acc_time, self.acc_energy, self.acc_cost, age,
        )

    # ── Coordinator update ─────────────────────────────────────────────────

    async def _async_update_data(self) -> dict[str, Any]:
        """Called by the coordinator at regular intervals.

        Fix 7 — concurrent guard: if a previous poll is still running (e.g.
        InfluxDB is slow), skip this cycle rather than running two overlapping
        updates which could cause double-writes.
        """
        if self._update_lock.locked():
            _LOGGER.debug("Previous update still running — skipping this poll")
            return self._get_data()

        async with self._update_lock:
            now = time.time()

            _now_local = datetime.now(ZoneInfo(LOCAL_TIMEZONE))
            current_month = _now_local.month
            current_day = _now_local.date()
            if current_month != self.last_month:
                _LOGGER.info(
                    "Month rolled over (%d → %d) — resetting monthly totals and reloading from HA statistics",
                    self.last_month, current_month,
                )
                self._monthly_tracker.reset()
                self._price_fallback_count = 0
                # v2.14.0 — a new month starts fresh, so last month's baseline
                # floor must NOT carry over (it would wrongly inflate the new
                # month's totals via the max()-style floor in
                # _async_load_monthly_data()).
                self._persisted_monthly_baseline = {}
                if self._store is not None:
                    self._store.save_monthly_baseline_in_memory(self.monthly)
                    await self._store.async_flush_monthly_baseline()
                await self._async_load_monthly_data()
                self.last_month = current_month

            if current_day != self.last_day:
                _LOGGER.info(
                    "Day rolled over (%s → %s) — resetting daily totals and reloading from HA statistics",
                    self.last_day, current_day,
                )
                self._daily_tracker.reset()
                # New day starts fresh — last day's baseline floor must not
                # carry over (same reasoning as the monthly reset above).
                self._persisted_daily_baseline = {}
                if self._store is not None:
                    self._store.save_daily_baseline_in_memory(self.daily)
                    await self._store.async_flush_daily_baseline()
                await self._async_load_daily_data()
                self.last_day = current_day

            if self._monthly_loaded:
                await self._calculate_deltas(now)
                self.last_time = now
            else:
                _LOGGER.debug("Monthly data not yet loaded — skipping delta apply this poll")

            try:
                nm = self.hass.data.get(DOMAIN, {}).get("notification_manager")
                if nm:
                    await nm.async_evaluate(self)
            except Exception as err:
                _LOGGER.warning("Notification evaluation error: %s", err)

            return self._get_data()

    # ── State change handling ──────────────────────────────────────────────

    @callback
    def _handle_state_change(self, event) -> None:
        """Sync callback — dispatched only for the two tracked entity IDs."""
        self.hass.async_create_task(self._async_handle_state_change(event))

    async def _async_handle_state_change(self, event) -> None:
        """Async handler for user/power state changes."""
        entity_id = event.data.get("entity_id")
        now = time.time()

        if entity_id == self._user_entity:
            await self._handle_user_change(event, now)
        elif entity_id == self._watt_entity and self.current_user:
            await self._handle_power_change(now)
            self.last_time = now

        self.async_set_updated_data(self._get_data())

    async def _handle_user_change(self, event, now: float) -> None:
        """Handle user sensor state change."""
        new_state = event.data.get("new_state")

        if new_state is None or new_state.state in ("unavailable", "unknown"):
            user_key = None
        else:
            user_key = new_state.state.lower()

        raw_mapped = self.user_map.get(user_key) if user_key is not None else None

        if isinstance(raw_mapped, dict):
            _LOGGER.warning(
                "user_map returned a dict for key '%s' — normalizing on the fly: %s",
                user_key, raw_mapped,
            )
            new_user: str | None = raw_mapped.get("user_id") or None
        elif isinstance(raw_mapped, str) and raw_mapped:
            new_user = raw_mapped
        else:
            new_user = None

        same_user_relogin = (
            new_user is not None
            and new_user == self.current_user
            and (now - self.last_time) > 600
        )

        if new_user != self.current_user or same_user_relogin:
            if same_user_relogin:
                _LOGGER.info(
                    "Same-user re-login detected for '%s' (PC shut down without logout) "
                    "— starting new session, resetting accumulators",
                    new_user,
                )
            else:
                _LOGGER.info("User changed: %s → %s", self.current_user, new_user)

            if self.current_user and not same_user_relogin:
                await self._calculate_deltas(now)

            self.current_user = new_user
            if new_user:
                self._idle_since = None
                self.acc_time = 0.0
                self.acc_energy = 0.0
                self.acc_cost = 0.0
                self.last_power = self._get_power()

                store = self.hass.data.get(DOMAIN, {}).get("store")
                if store:
                    store.reset_session_sent(new_user)

                _store = self.hass.data.get(DOMAIN, {}).get("store")
                if _store:
                    _store.save_session_in_memory(new_user, 0.0, 0.0, 0.0, now)
                    self.hass.async_create_task(_store.async_flush_session())
            else:
                self._idle_since = now
                self.last_power = 0.0  # Reset stale power reading on logout
                _store = self.hass.data.get(DOMAIN, {}).get("store")
                if _store:
                    self.hass.async_create_task(_store.async_clear_session())

            self.last_time = now
            self.last_write_time = now

    async def _handle_power_change(self, now: float) -> None:
        """Handle power sensor state change."""
        await self._calculate_deltas(now)

    # ── Delta calculation ──────────────────────────────────────────────────

    async def _calculate_deltas(self, now: float) -> None:
        """Accumulate time/energy/cost deltas into the monthly/daily trackers.

        v2.17.0: no longer writes anywhere. self.monthly/self.daily update
        directly via apply_delta() below every poll — the monthly_*/daily
        sensors' own state updates are what HA's recorder observes to build
        the long-term statistics _async_sum_period_from_statistics() reads
        back. There's no separate WRITE_THRESHOLD-gated commit step anymore;
        apply_delta() already ran unconditionally on every poll before this
        change too (only the now-removed InfluxDB write was threshold-gated).
        """
        if not self.current_user:
            return

        if not isinstance(self.current_user, str):
            _LOGGER.error(
                "_calculate_deltas: current_user is not a string (%s), resetting",
                type(self.current_user).__name__,
            )
            self.current_user = None
            return

        delta_time = now - self.last_time
        if delta_time <= 0:
            _LOGGER.debug("Non-positive delta_time: %s, skipping", delta_time)
            return

        current_power = self._get_power()
        avg_power     = (current_power + self.last_power) / 2
        energy_delta  = avg_power * delta_time / 3_600_000  # W·s → kWh
        price         = self._get_price()
        cost_delta    = energy_delta * price

        self.acc_time   += delta_time
        self.acc_energy += energy_delta
        self.acc_cost   += cost_delta

        self._monthly_tracker.apply_delta(self.current_user, delta_time, energy_delta, cost_delta)
        self._daily_tracker.apply_delta(self.current_user, delta_time, energy_delta, cost_delta)

        # "last update" timestamp for ws_get_system/ws_get_health — no longer
        # gates a write, just reports liveness.
        self.last_write_time = now
        self.last_power = current_power

    # ── Sensor helpers ─────────────────────────────────────────────────────

    def _get_power(self) -> float:
        """Net PC power = watt sensor minus meter device overhead."""
        watt_state   = self.hass.states.get(self._watt_entity)
        device_state = self.hass.states.get(self._device_entity)
        watt         = safe_float_from_state(watt_state,   default=0.0, min_value=0.0)
        device_power = safe_float_from_state(device_state, default=0.0, min_value=0.0)
        return max(watt - device_power, 0.0)

    def _get_price(self) -> float:
        """Current energy price in DKK/kWh.

        Falls back to the last known valid price if the price sensor is
        temporarily unavailable/unknown/unparsable, instead of silently
        treating the period as free (0.0 DKK/kWh) — which previously caused
        cost to be undercounted while time/energy kept accumulating normally.
        Only returns 0.0 if no valid price has ever been read (e.g. right
        after HA startup, before the price sensor has reported for the
        first time and no cached value was restored from the session
        snapshot).

        Fallback usage is counted (self._price_fallback_count, visible in the
        Admin tab via ws_get_health) and a warning is logged at most once per
        PRICE_FALLBACK_LOG_INTERVAL seconds, so a sensor outage is discoverable
        instead of silent.
        """
        price_state = self.hass.states.get(self._price_entity)
        if price_state is not None and price_state.state not in (
            "unavailable", "unknown", "none", "",
        ):
            try:
                value = float(price_state.state)
            except (ValueError, TypeError):
                value = None
            if value is not None and value >= 0:
                self._last_valid_price = value
                self._last_valid_price_time = time.time()
                return value

        # Price sensor unavailable, unknown, or unparsable — fall back.
        self._price_fallback_count += 1
        now = time.time()
        if now - self._last_price_warning_time > PRICE_FALLBACK_LOG_INTERVAL:
            _LOGGER.warning(
                "Price entity '%s' unavailable/invalid — using last known price "
                "%.2f kr/kWh (fallback used %d time(s) this month)",
                self._price_entity, self._last_valid_price, self._price_fallback_count,
            )
            self._last_price_warning_time = now
        return self._last_valid_price

    def _is_price_entity_ok(self) -> bool:
        """Return True if the price entity currently holds a valid, parsable state.

        Used by ws_get_health to show live price-sensor status on the Admin tab,
        independent of whether a fallback happened to be used on the last delta.
        """
        state = self.hass.states.get(self._price_entity)
        if state is None or state.state in ("unavailable", "unknown", "none", ""):
            return False
        try:
            return float(state.state) >= 0
        except (ValueError, TypeError):
            return False

    # ── Manual corrections (v2.17.0 — no more InfluxDB write) ───────────────

    async def async_add_manual_entry(
        self,
        user: str,
        timestamp_ns: int,
        time_delta: float,
        energy_delta: float = 0.0,
        cost_delta: float = 0.0,
    ) -> bool:
        """Apply a manual time/energy/cost correction for a missed session.

        Used by ws_add_manual_entry for ad-hoc fixes when a session was lost
        (e.g. files were overwritten mid-session, causing data loss).

        v2.17.0: applies the correction directly to the in-memory monthly/
        daily trackers (via apply_delta, same as a normal poll) instead of
        writing a tagged InfluxDB point and reloading. Known limitation vs.
        the old InfluxDB-backed version: this only affects totals for the
        period(s) the correction's date actually falls in — a correction
        dated in a PAST calendar month/day is not retroactively reflected in
        the history graph either, since HA's own long-term statistics are
        derived from real sensor state history and can't be backfilled for a
        bygone day the way a raw InfluxDB point could. The documented use
        case (a session lost same-day/same-month) is unaffected.
        """
        if user not in self.tracked_users:
            return False

        correction_local = datetime.fromtimestamp(
            timestamp_ns / 1_000_000_000, tz=timezone.utc
        ).astimezone(ZoneInfo(LOCAL_TIMEZONE))
        now_local = datetime.now(ZoneInfo(LOCAL_TIMEZONE))

        applied_to: list[str] = []
        if (correction_local.year, correction_local.month) == (now_local.year, now_local.month):
            self._monthly_tracker.apply_delta(user, time_delta, energy_delta, cost_delta)
            applied_to.append("monthly")
        if correction_local.date() == now_local.date():
            self._daily_tracker.apply_delta(user, time_delta, energy_delta, cost_delta)
            applied_to.append("daily")

        if not applied_to:
            _LOGGER.warning(
                "Manual entry for %s dated %s falls outside the current month — "
                "not applied (HA long-term statistics can't be backfilled for a past day)",
                user, correction_local.date(),
            )
            return False

        _LOGGER.info(
            "Manual correction applied (%s): user=%s time=+%.0fs energy=+%.4fkWh cost=+%.4fDKK",
            "+".join(applied_to), user, time_delta, energy_delta, cost_delta,
        )
        if self._store is not None:
            if "monthly" in applied_to:
                self._store.save_monthly_baseline_in_memory(self.monthly)
                await self._store.async_flush_monthly_baseline()
            if "daily" in applied_to:
                self._store.save_daily_baseline_in_memory(self.daily)
                await self._store.async_flush_daily_baseline()
        return True

    # ── Data snapshot ──────────────────────────────────────────────────────

    def _get_data(self) -> dict[str, Any]:
        """Return current data snapshot for coordinator listeners and sensors."""
        monthly_view = self._monthly_tracker.view()
        daily_view = self._daily_tracker.view()

        return {
            "current_user":   self.current_user,
            "acc_time":       self.acc_time,
            "acc_energy":     self.acc_energy,
            "acc_cost":       self.acc_cost,
            "monthly":        monthly_view,
            "monthly_loaded": self._monthly_loaded,
            "daily":          daily_view,
            "daily_loaded":   self._daily_loaded,
            "price_fallback_count": self._price_fallback_count,
            "last_valid_price":     self._last_valid_price,
            "price_entity_ok":      self._is_price_entity_ok(),
        }
