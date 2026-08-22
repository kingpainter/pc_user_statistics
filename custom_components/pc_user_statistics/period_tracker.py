# File Name: period_tracker.py
# Version: 1.0.0
# Description: Shared bookkeeping for rollover-period totals (monthly / daily).
# Added: PC User Statistics v2.16.0
#
# Background:
#   __init__.py had two nearly-identical parallel implementations of the same
#   logic — self.monthly/self._pending (added v2.x) and self.daily/
#   self._daily_pending (added v2.15.0, copy-pasted from the monthly version).
#   Both track: an in-memory totals dict, a "pending" buffer used before the
#   first InfluxDB load completes, a "loaded" flag, and a baseline-floor merge
#   against persisted data (store.py get_monthly_baseline / get_daily_baseline).
#   Since the two copies had to be kept in sync by hand, the daily tracker was
#   itself born from a bug caused by that duplication (MS Family Safety
#   comparison silently using the monthly total). This module collects the
#   pure bookkeeping into one place so a future third period (or a fix to this
#   logic) only has to be written once.
#
#   Deliberately contains NO I/O — no InfluxDB queries, no NotificationStore
#   reads/writes, no aiohttp. That stays in the coordinator (__init__.py),
#   which owns the HTTP session and the store reference. Keeping this class
#   pure means it can be unit tested without mocking HTTP or HA storage.

from __future__ import annotations

import logging
from typing import Literal

_LOGGER = logging.getLogger(__name__)

_METRIC_KEYS: tuple[str, ...] = ("time", "energy", "cost")


def _empty_totals(users: list[str]) -> dict[str, dict[str, float]]:
    """Return a fresh zeroed totals dict for the given users."""
    return {user: {"time": 0.0, "energy": 0.0, "cost": 0.0} for user in users}


class PeriodTracker:
    """Tracks accumulated time/energy/cost totals for one rollover period.

    `period` is only used for log messages ("Monthly ..." / "Daily ...") —
    no behavioral branching depends on it.
    """

    def __init__(self, period: Literal["month", "day"], tracked_users: list[str]) -> None:
        self.period = period
        self.tracked_users: list[str] = list(tracked_users)
        self.totals: dict[str, dict[str, float]] = _empty_totals(self.tracked_users)
        self.pending: dict[str, dict[str, float]] = _empty_totals(self.tracked_users)
        self.loaded: bool = False

    def reset(self) -> None:
        """Zero totals and pending, and mark as not-yet-loaded.

        Called on rollover (new month / new day) — the caller is responsible
        for also clearing any persisted baseline floor (self._persisted_*_baseline
        in the coordinator) so the new period doesn't inherit the old one's floor.
        """
        self.totals = _empty_totals(self.tracked_users)
        self.pending = _empty_totals(self.tracked_users)
        self.loaded = False

    def apply_delta(
        self, user: str, time_delta: float, energy_delta: float, cost_delta: float
    ) -> None:
        """Accumulate a delta into totals (if loaded) or pending (if not yet loaded).

        No-op if `user` is not in tracked_users — mirrors the previous
        `if user in target:` guard inline in the coordinator.
        """
        target = self.totals if self.loaded else self.pending
        if user in target:
            target[user]["time"] += time_delta
            target[user]["energy"] += energy_delta
            target[user]["cost"] += cost_delta

    def view(self) -> dict[str, dict[str, float]]:
        """Return the current best-known totals.

        While not yet loaded, this is totals (all zero) + pending merged, so
        callers (coordinator._get_data -> sensors/websocket) see live
        in-session numbers even before the first InfluxDB load completes.
        """
        if self.loaded:
            return self.totals
        return {
            user: {
                key: self.totals[user][key] + self.pending.get(user, {}).get(key, 0.0)
                for key in _METRIC_KEYS
            }
            for user in self.tracked_users
        }

    def _floor_merge(
        self,
        raw: dict[str, dict[str, float]],
        baseline: dict[str, dict[str, float]],
    ) -> dict[str, dict[str, float]]:
        """Apply the baseline floor to a fresh InfluxDB result, per user/metric.

        A fresh InfluxDB sum is never allowed to be LOWER than the persisted
        baseline — a lower value at this point means InfluxDB is missing
        recent writes (e.g. stuck in the RAM-only failed-writes buffer during
        an outage), not that the true total decreased.
        """
        merged = _empty_totals(self.tracked_users)
        for user in self.tracked_users:
            raw_user = raw.get(user, {})
            baseline_user = baseline.get(user, {})
            for key in _METRIC_KEYS:
                raw_val = float(raw_user.get(key, 0.0) or 0.0)
                floor_val = float(baseline_user.get(key, 0.0) or 0.0)
                if raw_val < floor_val:
                    _LOGGER.warning(
                        "%s %s for '%s' from InfluxDB (%.2f) is lower than the "
                        "last known baseline (%.2f) — keeping the higher value. "
                        "This usually means InfluxDB is missing recent writes "
                        "(e.g. after an outage) rather than the true total "
                        "having decreased.",
                        self.period.capitalize(), key, user, raw_val, floor_val,
                    )
                    raw_val = floor_val
                merged[user][key] = raw_val
        return merged

    def load_from_influx(
        self,
        raw: dict[str, dict[str, float]],
        baseline: dict[str, dict[str, float]],
    ) -> None:
        """Finalize a successful InfluxDB load: floor-merge, fold in pending, mark loaded.

        Mirrors the previous inline behaviour in _async_load_monthly_data /
        _async_load_daily_data exactly: the freshly-fetched sum is
        floor-protected against `baseline`, then any deltas accumulated in
        `pending` while the load was in flight are added on top, then pending
        is cleared and totals becomes authoritative.
        """
        merged = self._floor_merge(raw, baseline)
        for user in self.tracked_users:
            pending_user = self.pending.get(user, {})
            for key in _METRIC_KEYS:
                merged[user][key] += pending_user.get(key, 0.0)

        self.totals = merged
        self.pending = _empty_totals(self.tracked_users)
        self.loaded = True

    def load_fallback(self, baseline: dict[str, dict[str, float]]) -> None:
        """Finalize a failed load (all InfluxDB retries exhausted): fall back to baseline.

        Used instead of resetting to zero, so a prolonged InfluxDB outage at
        startup doesn't visibly erase already-tracked totals.
        """
        self.totals = {
            user: {
                key: float(baseline.get(user, {}).get(key, 0.0) or 0.0)
                for key in _METRIC_KEYS
            }
            for user in self.tracked_users
        }
        self.loaded = True
