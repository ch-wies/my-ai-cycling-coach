"""Tests for src/analysis/activity_metrics.py"""

from typing import Any, Optional

import numpy as np
import pandas as pd
import pytest

from src.data.activity import Activity
from src.analysis.activity_metrics import (
    climbing_time_s,
    elevation_changes,
    grade_series,
    heart_rate_recovery_60s,
    moving_mask,
    normalized_power,
    pedaling_mask,
    representative_dt,
    sample_weights,
    stop_durations,
    time_summary,
    total_work_kj,
    weighted_average,
)


def _activity(
    streams: dict[str, np.ndarray],
    dt: float = 1.0,
    elapsed: Optional[float] = None,
    moving_time: Optional[float] = None,
    times: Optional[np.ndarray] = None,
) -> Activity:
    n = len(next(iter(streams.values())))
    t = times if times is not None else np.arange(n) * dt
    data: dict[str, Any] = {
        "timestamp": pd.to_datetime(0, unit="s") + pd.to_timedelta(t, unit="s")
    }
    data.update(streams)
    return Activity(
        sport="Ride",
        total_elapsed_time=elapsed,
        total_moving_time=moving_time,
        data=pd.DataFrame(data),
    )


# ---------------------------------------------------------------------------
# representative_dt
# ---------------------------------------------------------------------------


class TestRepresentativeDt:
    def test_uniform_1hz(self) -> None:
        assert representative_dt(np.arange(100, dtype=float)) == 1.0

    def test_uniform_4s(self) -> None:
        assert representative_dt(np.arange(0, 400, 4, dtype=float)) == 4.0

    def test_ignores_leading_gap(self) -> None:
        # first delta is a 300 s gap; the rest are 1 s — median should be 1
        t = np.concatenate([[0.0, 300.0], 300.0 + np.arange(1, 50)])
        assert representative_dt(t) == 1.0

    def test_too_short_defaults_to_one(self) -> None:
        assert representative_dt(np.array([5.0])) == 1.0


# ---------------------------------------------------------------------------
# sample_weights
# ---------------------------------------------------------------------------


class TestSampleWeights:
    def test_uniform_weights_sum_to_span_plus_one_sample(self) -> None:
        t = np.arange(10, dtype=float)
        w = sample_weights(t)
        assert np.allclose(w, 1.0)

    def test_gap_clamped_to_median(self) -> None:
        # 1 Hz for 5 samples, then a 600 s pause, then 1 Hz again
        t = np.array([0, 1, 2, 3, 4, 604, 605, 606], dtype=float)
        w = sample_weights(t)
        # the post-gap sample must NOT carry the 600 s gap
        assert w[5] == 1.0
        assert w.max() == 1.0

    def test_single_sample(self) -> None:
        assert sample_weights(np.array([0.0])).tolist() == [1.0]


# ---------------------------------------------------------------------------
# moving_mask / time_summary
# ---------------------------------------------------------------------------


def _speed(*runs: tuple[float, int]) -> np.ndarray:
    return np.concatenate([np.full(count, value) for value, count in runs])


class TestMovingMask:
    def test_speed_above_zero_is_moving(self) -> None:
        act = _activity({"speed": np.array([0.0, 0.03, 5.0, 0.0])})
        mask = moving_mask(act)
        assert mask is not None
        assert mask.tolist() == [False, True, True, False]

    def test_ignores_moving_column(self) -> None:
        act = _activity(
            {"speed": np.array([5.0, 0.0]), "moving": np.array([False, True])}
        )
        mask = moving_mask(act)
        assert mask is not None
        assert mask.tolist() == [True, False]

    def test_no_speed_column(self) -> None:
        assert moving_mask(_activity({"power": np.full(10, 200.0)})) is None

    def test_empty_speed(self) -> None:
        assert moving_mask(_activity({"speed": np.array([])})) is None

    def test_nan_speed_is_not_moving(self) -> None:
        mask = moving_mask(_activity({"speed": np.array([5.0, np.nan, 5.0])}))
        assert mask is not None
        assert mask.tolist() == [True, False, True]


class TestStopDurations:
    def test_minimum_stop_duration(self) -> None:
        speed = _speed((5, 20), (0, 5), (5, 20), (0, 10), (5, 20), (0, 60), (5, 20))
        t = np.arange(len(speed), dtype=float)
        assert stop_durations(t, speed > 0) == pytest.approx([10.0, 60.0])

    def test_leading_and_trailing_stops_included(self) -> None:
        speed = _speed((0, 15), (5, 30), (0, 12))
        t = np.arange(len(speed), dtype=float)
        assert stop_durations(t, speed > 0) == pytest.approx([15.0, 12.0])

    def test_threshold_uses_durations_not_sample_counts(self) -> None:
        # At 2 s sampling, 4 zero samples are 8 s (no stop), 5 are 10 s (stop).
        speed = _speed((5, 10), (0, 4), (5, 10), (0, 5), (5, 10))
        t = np.arange(len(speed), dtype=float) * 2.0
        assert stop_durations(t, speed > 0) == pytest.approx([10.0])

    def test_recording_gap_is_a_stop(self) -> None:
        t = np.concatenate([np.arange(20.0), np.arange(20.0) + 19.0 + 30.0])
        mask = np.ones(len(t), dtype=bool)
        assert stop_durations(t, mask) == pytest.approx([29.0])

    def test_short_gap_is_not_a_stop(self) -> None:
        # 7 s delta: above the 5 s gap threshold, below MIN_STOP_S
        t = np.concatenate([np.arange(20.0), np.arange(20.0) + 19.0 + 7.0])
        mask = np.ones(len(t), dtype=bool)
        assert stop_durations(t, mask) == []

    def test_gap_merges_with_adjacent_zero_run(self) -> None:
        # 6 zero-speed samples, then a 6 s gap before moving resumes
        t = np.concatenate([np.arange(26.0), np.arange(20.0) + 25.0 + 6.0])
        speed = _speed((5, 20), (0, 6), (5, 20))
        assert stop_durations(t, speed > 0) == pytest.approx([11.0])

    def test_empty(self) -> None:
        assert stop_durations(np.array([]), np.array([], dtype=bool)) == []


class TestTimeSummary:
    def test_prefers_metadata_moving_time(self) -> None:
        act = _activity({"power": np.full(100, 200.0)}, elapsed=120, moving_time=100)
        s = time_summary(act)
        assert s["elapsed_s"] == 120
        assert s["moving_s"] == 100
        assert s["stopped_s"] == 20

    def test_moving_from_mask_when_no_metadata(self) -> None:
        act = _activity({"speed": _speed((5, 60), (0, 40))}, elapsed=99)
        s = time_summary(act)
        # 60 moving samples at 1 s each
        assert s["moving_s"] == pytest.approx(60.0)
        assert s["stops"] == 1

    def test_no_moving_info_omits_moving_keys(self) -> None:
        act = _activity({"power": np.full(50, 100.0)}, elapsed=49)
        s = time_summary(act)
        assert "moving_s" not in s
        assert s["elapsed_s"] == 49

    def test_counts_multiple_stops(self) -> None:
        speed = _speed((5, 20), (0, 15), (5, 20), (0, 15), (5, 20))
        assert time_summary(_activity({"speed": speed}))["stops"] == 2

    def test_stop_count_matches_stop_durations(self) -> None:
        speed = _speed((5, 20), (0, 3), (5, 20), (0, 12), (5, 40))
        t = np.arange(len(speed), dtype=float)
        t[70:] += 30.0  # recording gap in the last moving stretch
        act = _activity({"speed": speed}, times=t)
        assert time_summary(act)["stops"] == len(stop_durations(t, speed > 0)) == 2


# ---------------------------------------------------------------------------
# pedaling_mask
# ---------------------------------------------------------------------------


class TestPedalingMask:
    def test_uses_cadence_when_present(self) -> None:
        cadence = np.array([80.0] * 50 + [0.0] * 50)
        act = _activity({"cadence": cadence, "power": np.full(100, 200.0)})
        mask = pedaling_mask(act)
        assert mask is not None
        assert mask[:50].all()
        assert not mask[50:].any()

    def test_falls_back_to_power_without_cadence(self) -> None:
        power = np.array([200.0] * 60 + [0.0] * 40)
        act = _activity({"power": power})
        mask = pedaling_mask(act)
        assert mask is not None
        assert mask[:60].all()
        assert not mask[60:].any()

    def test_none_when_neither_stream(self) -> None:
        act = _activity({"heart_rate": np.full(50, 140.0)})
        assert pedaling_mask(act) is None


# ---------------------------------------------------------------------------
# elevation_changes
# ---------------------------------------------------------------------------


class TestElevationChanges:
    def test_pure_climb_then_descent(self) -> None:
        alt = np.concatenate([np.linspace(0, 100, 200), np.linspace(100, 0, 200)])
        t = np.arange(len(alt), dtype=float)
        ascent, descent = elevation_changes(alt, t)
        assert ascent == pytest.approx(100, abs=5)
        assert descent == pytest.approx(100, abs=5)

    def test_noise_does_not_explode(self) -> None:
        # flat with small jitter → both should stay tiny after smoothing
        rng = np.random.default_rng(0)
        alt = 50 + rng.normal(0, 0.3, 600)
        t = np.arange(len(alt), dtype=float)
        ascent, descent = elevation_changes(alt, t)
        assert ascent < 15
        assert descent < 15

    def test_handles_nan(self) -> None:
        alt = np.linspace(0, 50, 100)
        alt[40:50] = np.nan
        t = np.arange(len(alt), dtype=float)
        ascent, _ = elevation_changes(alt, t)
        assert ascent == pytest.approx(50, abs=5)

    def test_empty_returns_zero(self) -> None:
        assert elevation_changes(np.array([]), np.array([])) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# grade_series / climbing_time_s
# ---------------------------------------------------------------------------


class TestGradeSeries:
    def test_steady_climb_returns_constant_grade(self) -> None:
        n = 300
        distance = np.arange(n, dtype=float) * 8.0  # 8 m run per sample
        altitude = distance * 0.05  # exact 5% grade
        t = np.arange(n, dtype=float)
        grade = grade_series(altitude, distance, t)
        assert len(grade) == n
        assert np.isnan(grade[0])
        interior = grade[30:-30]
        assert np.all(~np.isnan(interior))
        assert interior == pytest.approx(5.0, abs=1.0)

    def test_flat_then_climb(self) -> None:
        n = 300
        flat = np.zeros(150)
        climb = np.linspace(0, 96, 150)  # 96 m rise over 150 * 8 m = 1200 m run → 8%
        altitude = np.concatenate([flat, climb])
        distance = np.arange(n, dtype=float) * 8.0
        t = np.arange(n, dtype=float)
        grade = grade_series(altitude, distance, t)
        flat_interior = grade[30:100]
        climb_interior = grade[180:270]
        assert np.all(np.abs(flat_interior) < 1.0)
        assert climb_interior == pytest.approx(8.0, abs=1.5)

    def test_stationary_section_returns_nan_not_spike(self) -> None:
        moving_distance = np.arange(100, dtype=float) * 8.0
        stationary_distance = np.full(100, moving_distance[-1])
        distance = np.concatenate([moving_distance, stationary_distance])
        altitude = np.concatenate([np.linspace(0, 10, 100), np.full(100, 10.0)])
        t = np.arange(200, dtype=float)
        grade = grade_series(altitude, distance, t)
        # distance stops advancing at index 100 → grade must go NaN, not spike
        assert np.all(np.isnan(grade[105:]))

    def test_nan_altitude_is_interpolated(self) -> None:
        n = 100
        altitude = np.linspace(0, 50, n)
        altitude[40:50] = np.nan
        distance = np.arange(n, dtype=float) * 8.0
        t = np.arange(n, dtype=float)
        grade = grade_series(altitude, distance, t)
        interior = grade[20:80]
        assert np.all(~np.isnan(interior))
        assert interior == pytest.approx(6.3, abs=1.0)

    def test_empty_returns_empty_array(self) -> None:
        assert len(grade_series(np.array([]), np.array([]), np.array([]))) == 0

    def test_missing_distance_returns_all_nan(self) -> None:
        altitude = np.linspace(0, 10, 50)
        grade = grade_series(altitude, np.array([]), np.arange(50, dtype=float))
        assert len(grade) == 50
        assert np.all(np.isnan(grade))


class TestClimbingTimeS:
    def test_sums_time_above_threshold(self) -> None:
        grade = np.zeros(100)
        grade[20:50] = 5.0  # 30 samples above the 3% default threshold
        t = np.arange(100, dtype=float)
        assert climbing_time_s(grade, t) == pytest.approx(30.0)

    def test_all_nan_returns_zero(self) -> None:
        grade = np.full(50, np.nan)
        t = np.arange(50, dtype=float)
        assert climbing_time_s(grade, t) == 0.0

    def test_all_below_threshold_returns_zero(self) -> None:
        grade = np.full(50, 1.0)
        t = np.arange(50, dtype=float)
        assert climbing_time_s(grade, t) == 0.0

    def test_custom_threshold(self) -> None:
        grade = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        t = np.arange(5, dtype=float)
        assert climbing_time_s(grade, t, threshold_pct=2.5) == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# normalized_power / total_work_kj / weighted_average
# ---------------------------------------------------------------------------


class TestPowerMetrics:
    def test_np_of_constant_power_equals_power(self) -> None:
        t = np.arange(600, dtype=float)
        assert normalized_power(np.full(600, 250.0), t) == pytest.approx(250.0)

    def test_np_none_when_too_short(self) -> None:
        t = np.arange(10, dtype=float)
        assert normalized_power(np.full(10, 200.0), t) is None

    def test_work_kj(self) -> None:
        # 100 W for 100 s = 10000 J = 10 kJ
        t = np.arange(100, dtype=float)
        assert total_work_kj(np.full(100, 100.0), t) == pytest.approx(10.0, abs=0.2)

    def test_weighted_average_constant(self) -> None:
        t = np.arange(100, dtype=float)
        assert weighted_average(np.full(100, 150.0), t) == pytest.approx(150.0)

    def test_weighted_average_with_mask(self) -> None:
        t = np.arange(100, dtype=float)
        series = np.concatenate([np.full(50, 100.0), np.full(50, 200.0)])
        mask = np.array([True] * 50 + [False] * 50)
        assert weighted_average(series, t, mask) == pytest.approx(100.0)

    def test_weighted_average_ignores_nan(self) -> None:
        t = np.arange(100, dtype=float)
        series = np.full(100, 120.0)
        series[:50] = np.nan
        assert weighted_average(series, t) == pytest.approx(120.0)

    def test_weighted_average_empty_returns_none(self) -> None:
        assert weighted_average(np.array([]), np.array([])) is None


# ---------------------------------------------------------------------------
# heart_rate_recovery_60s
# ---------------------------------------------------------------------------


class TestHeartRateRecovery60s:
    def _clear_recovery_streams(
        self, n: int = 200, end_s: int = 100
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        t = np.arange(n, dtype=float)
        hr = np.full(n, 140.0)
        hr[end_s + 1 :] = 100.0  # sharp recovery drop right after the effort ends
        power = np.full(n, 250.0)
        power[end_s + 1 :] = 50.0  # rider backs off during recovery
        return hr, power, t

    def test_clear_recovery_returns_bpm_dropped(self) -> None:
        hr, power, t = self._clear_recovery_streams()
        hrr = heart_rate_recovery_60s(hr, power, t, end_s=100, ftp=250)
        assert hrr == pytest.approx(40.0)

    def test_next_interval_inside_window_returns_none(self) -> None:
        hr, power, t = self._clear_recovery_streams()
        assert (
            heart_rate_recovery_60s(hr, power, t, end_s=100, next_start_s=140, ftp=250)
            is None
        )

    def test_insufficient_trailing_data_returns_none(self) -> None:
        hr, power, t = self._clear_recovery_streams(n=150, end_s=100)
        assert heart_rate_recovery_60s(hr, power, t, end_s=100, ftp=250) is None

    def test_nan_hr_window_returns_none(self) -> None:
        hr, power, t = self._clear_recovery_streams()
        hr[95:106] = np.nan  # blanks out the end-of-effort window
        assert heart_rate_recovery_60s(hr, power, t, end_s=100, ftp=250) is None

    def test_sustained_power_returns_none_with_ftp(self) -> None:
        hr, power, t = self._clear_recovery_streams()
        power[100:] = 200.0  # 80% FTP, above the 55% backoff threshold
        assert heart_rate_recovery_60s(hr, power, t, end_s=100, ftp=250) is None

    def test_sustained_power_returns_none_with_no_ftp_fallback(self) -> None:
        hr, power, t = self._clear_recovery_streams()
        power[100:] = 200.0  # above 0.5 * interval_avg_power=250 => 125
        assert (
            heart_rate_recovery_60s(hr, power, t, end_s=100, interval_avg_power=250.0)
            is None
        )

    def test_low_power_passes_no_ftp_fallback(self) -> None:
        hr, power, t = self._clear_recovery_streams()
        assert heart_rate_recovery_60s(
            hr, power, t, end_s=100, interval_avg_power=250.0
        ) == pytest.approx(40.0)

    def test_median_ignores_outlier_in_recovery_window(self) -> None:
        # A single glitchy sample (e.g. a dropped-then-recovered HR strap
        # reading) within the +60s window should not skew the result the way
        # a mean would.
        hr, power, t = self._clear_recovery_streams()
        hr[158] = 180.0
        hrr = heart_rate_recovery_60s(hr, power, t, end_s=100, ftp=250)
        assert hrr == pytest.approx(40.0)
