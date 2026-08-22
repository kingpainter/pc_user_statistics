# File Name: test_period_tracker.py
# Description: Unit tests for period_tracker.PeriodTracker — the shared
#              monthly/daily bookkeeping extracted from __init__.py v2.16.0.
#
# These tests need no HA mocking at all (PeriodTracker has zero I/O), unlike
# most of test_init.py which requires MagicMock hass/coordinator scaffolding.

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from custom_components.pc_user_statistics.period_tracker import PeriodTracker


class TestInitialState:

    def test_starts_zeroed_and_not_loaded(self):
        t = PeriodTracker("month", ["flemming", "lukas"])
        assert t.loaded is False
        assert t.totals == {
            "flemming": {"time": 0.0, "energy": 0.0, "cost": 0.0},
            "lukas": {"time": 0.0, "energy": 0.0, "cost": 0.0},
        }
        assert t.pending == t.totals

    def test_period_label_stored(self):
        assert PeriodTracker("month", []).period == "month"
        assert PeriodTracker("day", []).period == "day"

    def test_tracked_users_copied_not_aliased(self):
        users = ["flemming"]
        t = PeriodTracker("month", users)
        users.append("lukas")
        assert t.tracked_users == ["flemming"]  # unaffected by later mutation


class TestApplyDelta:

    def test_accumulates_into_pending_before_load(self):
        t = PeriodTracker("month", ["flemming"])
        t.apply_delta("flemming", time_delta=60.0, energy_delta=0.1, cost_delta=0.3)
        assert t.pending["flemming"] == {"time": 60.0, "energy": 0.1, "cost": 0.3}
        assert t.totals["flemming"] == {"time": 0.0, "energy": 0.0, "cost": 0.0}

    def test_accumulates_into_totals_after_load(self):
        t = PeriodTracker("month", ["flemming"])
        t.loaded = True
        t.apply_delta("flemming", time_delta=60.0, energy_delta=0.1, cost_delta=0.3)
        assert t.totals["flemming"] == {"time": 60.0, "energy": 0.1, "cost": 0.3}
        assert t.pending["flemming"] == {"time": 0.0, "energy": 0.0, "cost": 0.0}

    def test_multiple_deltas_accumulate(self):
        t = PeriodTracker("month", ["flemming"])
        t.loaded = True
        t.apply_delta("flemming", 60.0, 0.1, 0.3)
        t.apply_delta("flemming", 30.0, 0.05, 0.15)
        assert t.totals["flemming"]["time"] == 90.0
        assert round(t.totals["flemming"]["energy"], 5) == 0.15
        assert round(t.totals["flemming"]["cost"], 5) == 0.45

    def test_unknown_user_is_noop(self):
        t = PeriodTracker("month", ["flemming"])
        t.loaded = True
        t.apply_delta("sebastian", 60.0, 0.1, 0.3)  # not tracked
        assert "sebastian" not in t.totals


class TestView:

    def test_view_returns_totals_when_loaded(self):
        t = PeriodTracker("month", ["flemming"])
        t.loaded = True
        t.totals["flemming"] = {"time": 100.0, "energy": 1.0, "cost": 2.0}
        assert t.view() == {"flemming": {"time": 100.0, "energy": 1.0, "cost": 2.0}}

    def test_view_merges_pending_when_not_loaded(self):
        t = PeriodTracker("month", ["flemming"])
        t.totals["flemming"] = {"time": 10.0, "energy": 0.1, "cost": 0.2}
        t.pending["flemming"] = {"time": 5.0, "energy": 0.05, "cost": 0.1}
        view = t.view()
        assert view["flemming"]["time"] == 15.0
        assert round(view["flemming"]["energy"], 5) == 0.15
        assert round(view["flemming"]["cost"], 5) == 0.3

    def test_view_does_not_mutate_totals_or_pending(self):
        t = PeriodTracker("month", ["flemming"])
        t.pending["flemming"] = {"time": 5.0, "energy": 0.0, "cost": 0.0}
        t.view()
        assert t.totals["flemming"]["time"] == 0.0  # untouched


class TestReset:

    def test_reset_zeroes_totals_and_pending_and_marks_unloaded(self):
        t = PeriodTracker("month", ["flemming"])
        t.loaded = True
        t.totals["flemming"] = {"time": 100.0, "energy": 1.0, "cost": 2.0}
        t.pending["flemming"] = {"time": 5.0, "energy": 0.1, "cost": 0.2}
        t.reset()
        assert t.loaded is False
        assert t.totals["flemming"] == {"time": 0.0, "energy": 0.0, "cost": 0.0}
        assert t.pending["flemming"] == {"time": 0.0, "energy": 0.0, "cost": 0.0}


class TestLoadFromInflux:

    def test_raw_influx_result_becomes_totals(self):
        t = PeriodTracker("month", ["flemming"])
        raw = {"flemming": {"time": 3600.0, "energy": 1.0, "cost": 3.0}}
        t.load_from_influx(raw, baseline={})
        assert t.totals["flemming"] == {"time": 3600.0, "energy": 1.0, "cost": 3.0}
        assert t.loaded is True

    def test_pending_deltas_are_folded_in(self):
        t = PeriodTracker("month", ["flemming"])
        t.pending["flemming"] = {"time": 60.0, "energy": 0.1, "cost": 0.3}
        raw = {"flemming": {"time": 3600.0, "energy": 1.0, "cost": 3.0}}
        t.load_from_influx(raw, baseline={})
        assert t.totals["flemming"]["time"] == 3660.0
        assert round(t.totals["flemming"]["energy"], 5) == 1.1
        assert round(t.totals["flemming"]["cost"], 5) == 3.3

    def test_pending_cleared_after_load(self):
        t = PeriodTracker("month", ["flemming"])
        t.pending["flemming"] = {"time": 60.0, "energy": 0.1, "cost": 0.3}
        t.load_from_influx({"flemming": {"time": 0.0, "energy": 0.0, "cost": 0.0}}, baseline={})
        assert t.pending["flemming"] == {"time": 0.0, "energy": 0.0, "cost": 0.0}

    def test_baseline_floor_protects_against_lower_influx_value(self):
        """The v2.14.0 bug this guards against: InfluxDB missing recent writes
        must never make totals go DOWN — the baseline wins."""
        t = PeriodTracker("month", ["flemming"])
        raw = {"flemming": {"time": 1000.0, "energy": 0.5, "cost": 1.5}}
        baseline = {"flemming": {"time": 5000.0, "energy": 2.0, "cost": 6.0}}
        t.load_from_influx(raw, baseline)
        assert t.totals["flemming"] == {"time": 5000.0, "energy": 2.0, "cost": 6.0}

    def test_influx_value_above_baseline_is_kept(self):
        t = PeriodTracker("month", ["flemming"])
        raw = {"flemming": {"time": 9000.0, "energy": 3.0, "cost": 9.0}}
        baseline = {"flemming": {"time": 5000.0, "energy": 2.0, "cost": 6.0}}
        t.load_from_influx(raw, baseline)
        assert t.totals["flemming"] == {"time": 9000.0, "energy": 3.0, "cost": 9.0}

    def test_floor_applied_per_metric_independently(self):
        """time can be above baseline while energy is below it, etc. — each
        metric is floored independently, not the whole record at once."""
        t = PeriodTracker("month", ["flemming"])
        raw = {"flemming": {"time": 9000.0, "energy": 1.0, "cost": 9.0}}
        baseline = {"flemming": {"time": 5000.0, "energy": 2.0, "cost": 6.0}}
        t.load_from_influx(raw, baseline)
        assert t.totals["flemming"]["time"] == 9000.0   # influx wins
        assert t.totals["flemming"]["energy"] == 2.0     # baseline wins
        assert t.totals["flemming"]["cost"] == 9.0        # influx wins

    def test_missing_user_in_raw_defaults_to_zero(self):
        t = PeriodTracker("month", ["flemming", "lukas"])
        raw = {"flemming": {"time": 100.0, "energy": 0.1, "cost": 0.3}}  # lukas missing
        t.load_from_influx(raw, baseline={})
        assert t.totals["lukas"] == {"time": 0.0, "energy": 0.0, "cost": 0.0}

    def test_missing_user_in_baseline_defaults_to_zero_floor(self):
        t = PeriodTracker("month", ["flemming"])
        raw = {"flemming": {"time": 100.0, "energy": 0.1, "cost": 0.3}}
        t.load_from_influx(raw, baseline={})  # no baseline at all
        assert t.totals["flemming"] == {"time": 100.0, "energy": 0.1, "cost": 0.3}


class TestLoadFallback:

    def test_fallback_uses_baseline_values(self):
        t = PeriodTracker("month", ["flemming"])
        baseline = {"flemming": {"time": 1234.0, "energy": 5.0, "cost": 15.0}}
        t.load_fallback(baseline)
        assert t.totals["flemming"] == {"time": 1234.0, "energy": 5.0, "cost": 15.0}
        assert t.loaded is True

    def test_fallback_with_empty_baseline_zeroes_out(self):
        t = PeriodTracker("month", ["flemming"])
        t.load_fallback({})
        assert t.totals["flemming"] == {"time": 0.0, "energy": 0.0, "cost": 0.0}
        assert t.loaded is True

    def test_fallback_does_not_touch_pending(self):
        """Matches previous inline behaviour: pending is left as-is on the
        fallback path (not cleared) — same as before the refactor."""
        t = PeriodTracker("month", ["flemming"])
        t.pending["flemming"] = {"time": 30.0, "energy": 0.0, "cost": 0.0}
        t.load_fallback({})
        assert t.pending["flemming"]["time"] == 30.0


class TestMonthlyDailyIndependence:
    """Two separate PeriodTracker instances never share state — this is the
    whole point of the refactor (the v2.15.0 daily tracker bug was born from
    monthly/daily state being conflated in hand-duplicated code)."""

    def test_two_instances_are_fully_independent(self):
        monthly = PeriodTracker("month", ["flemming"])
        daily = PeriodTracker("day", ["flemming"])

        monthly.loaded = True
        monthly.totals["flemming"] = {"time": 360000.0, "energy": 50.0, "cost": 150.0}

        assert daily.loaded is False
        assert daily.totals["flemming"] == {"time": 0.0, "energy": 0.0, "cost": 0.0}
