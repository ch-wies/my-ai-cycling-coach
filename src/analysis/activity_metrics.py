"""Shared activity-level metrics: time accounting, elevation, and load primitives.

Centralises the logic that several AI tools (and the UI) need so it lives in one
place. Two design decisions worth knowing:

* Sampling is **not** assumed to be uniform. Recordings can be sub-1 Hz, and
  pauses (manual or Garmin Auto-Pause) appear as *gaps* in the time stream — the
  samples simply stop and resume later. We therefore derive per-sample time
  weights from the actual timestamps and clamp gaps so a pause's duration is
  never attributed to the single sample that follows it.

* "Moving" is derived as ``speed > 0``. The data source exposes no per-sample
  moving stream, but the recording device already does the stop detection:
  speed is exactly 0 while stopped, with no GPS jitter (checked on Garmin
  recordings; the result matches intervals.icu's ``moving_time``). Without a
  speed stream, moving-only stats are omitted rather than guessed.
"""

from typing import Optional

import numpy as np
import pandas as pd

from src.data.activity import Activity

# A time delta larger than GAP_FACTOR x the median sampling interval (but at
# least MIN_GAP_SECONDS) is treated as a pause gap rather than a real sample.
GAP_FACTOR = 3.0
MIN_GAP_SECONDS = 5.0

# Not-moving stretches shorter than this (track stands, slow hairpins, brief
# dropouts) are not counted as stops. Moving time still uses the raw mask.
MIN_STOP_S = 10.0


def representative_dt(time_array: np.ndarray) -> float:
    # Median of positive deltas, not time[1] - time[0] — the first delta is
    # not representative when the recording is non-uniform or starts with a gap.
    if time_array is None or len(time_array) < 2:
        return 1.0
    diffs = np.diff(np.asarray(time_array, dtype=float))
    diffs = diffs[diffs > 0]
    if len(diffs) == 0:
        return 1.0
    return float(np.median(diffs))


def _gap_threshold(med_dt: float) -> float:
    return max(GAP_FACTOR * med_dt, MIN_GAP_SECONDS)


def sample_weights(
    time_array: np.ndarray, gap_threshold: Optional[float] = None
) -> np.ndarray:
    # w[i] is the time the i-th sample represents (the interval preceding it).
    # Sample 0 and any pause gap are set to the median interval so a pause's
    # wall-clock duration is not charged to the sample that resumes recording.
    n = len(time_array) if time_array is not None else 0
    if n == 0:
        return np.array([])
    if n == 1:
        return np.array([1.0])

    med = representative_dt(time_array)
    if gap_threshold is None:
        gap_threshold = _gap_threshold(med)

    diffs = np.diff(np.asarray(time_array, dtype=float))
    w = np.empty(n)
    w[0] = med
    w[1:] = diffs
    w[(w > gap_threshold) | (w <= 0)] = med
    return w


def moving_mask(activity: Activity) -> Optional[np.ndarray]:
    speed = activity.get_time_series("speed")
    if speed is None or len(speed) == 0:
        return None
    return np.asarray(speed, dtype=float) > 0


def stop_durations(time_array: np.ndarray, mask: np.ndarray) -> list[float]:
    # A recording gap is not-moving time too (e.g. auto-pause during a café
    # stop), but sample_weights hides it, so the unassigned part of each gap
    # (delta - median dt) is added back here and merged with adjacent
    # mask-false samples into one stop.
    n = min(len(time_array), len(mask))
    if n == 0:
        return []
    t = np.asarray(time_array[:n], dtype=float)
    w = sample_weights(t)
    med = representative_dt(t)
    threshold = _gap_threshold(med)
    deltas = np.diff(t)

    stops: list[float] = []
    current = 0.0
    for i in range(n):
        if i > 0 and deltas[i - 1] > threshold:
            current += float(deltas[i - 1]) - med
        if not mask[i]:
            current += float(w[i])
        else:
            if current >= MIN_STOP_S:
                stops.append(current)
            current = 0.0
    if current >= MIN_STOP_S:
        stops.append(current)
    return stops


# At or above this cadence the rider is considered to be pedalling (below it,
# coasting). Used for both the coasting share and pedalling-only power.
PEDALING_CADENCE_RPM = 3


def pedaling_mask(
    activity: Activity, cadence_threshold: float = PEDALING_CADENCE_RPM
) -> Optional[np.ndarray]:
    cadence = activity.get_time_series("cadence")
    if cadence is not None and len(cadence) > 0:
        return (
            np.nan_to_num(np.asarray(cadence, dtype=float), nan=0.0)
            >= cadence_threshold
        )
    power = activity.get_time_series("power")
    if power is not None and len(power) > 0:
        return np.nan_to_num(np.asarray(power, dtype=float), nan=0.0) > 0
    return None


def time_summary(activity: Activity) -> dict:
    time_array = activity.get_time_array()
    elapsed = getattr(activity, "total_elapsed_time", None)
    if not elapsed:
        elapsed = float(time_array[-1] - time_array[0]) if len(time_array) > 1 else 0.0
    elapsed = float(elapsed)

    moving = getattr(activity, "total_moving_time", None)
    mask = moving_mask(activity)
    if moving is None and mask is not None:
        moving = float(np.sum(sample_weights(time_array)[: len(mask)][mask]))

    result = {"elapsed_s": elapsed}
    if moving is not None:
        moving = float(moving)
        result["moving_s"] = moving
        result["stopped_s"] = max(0.0, elapsed - moving)
    if mask is not None:
        result["stops"] = len(stop_durations(time_array, mask))
    return result


def _smoothed_altitude(
    altitude: np.ndarray, time_array: np.ndarray, smooth_window_s: float = 20.0
) -> np.ndarray:
    # NaNs are interpolated before smoothing so a single dropout doesn't punch a
    # hole in the rolling window. Centred rolling mean with min_periods=1 —
    # unlike a zero-padded convolution it introduces no edge bias, which would
    # otherwise fabricate ascent/descent (or grade) at the start/end of the ride.
    alt = np.asarray(altitude, dtype=float)
    valid = ~np.isnan(alt)
    if not valid.all() and valid.any():
        idx = np.arange(len(alt))
        alt = np.interp(idx, idx[valid], alt[valid])

    window = max(1, int(round(smooth_window_s / representative_dt(time_array))))
    return pd.Series(alt).rolling(window, center=True, min_periods=1).mean().to_numpy()


def elevation_changes(
    altitude: np.ndarray, time_array: np.ndarray, smooth_window_s: float = 20.0
) -> tuple[float, float]:
    if altitude is None or len(altitude) < 2:
        return 0.0, 0.0
    alt = np.asarray(altitude, dtype=float)
    if np.sum(~np.isnan(alt)) < 2:
        return 0.0, 0.0

    smoothed = _smoothed_altitude(alt, time_array, smooth_window_s)
    diffs = np.diff(smoothed)
    ascent = float(np.sum(diffs[diffs > 0]))
    descent = float(-np.sum(diffs[diffs < 0]))
    return ascent, descent


# Below this run (horizontal distance between consecutive smoothing-window
# points), a sample's grade is undefined rather than computed — this is what
# keeps stops/GPS distance jitter from producing spurious extreme grades.
MIN_GRADE_RUN_M = 1.0

# The smoothed grade above which a sample counts as "climbing" for
# climbing_time_s and the AI coach's avg-climbing-grade figure.
CLIMBING_GRADE_THRESHOLD_PCT = 3.0


def grade_series(
    altitude: np.ndarray,
    distance: np.ndarray,
    time_array: np.ndarray,
    smooth_window_s: float = 20.0,
) -> np.ndarray:
    # rise / run * 100, from smoothed altitude (suppresses GPS/barometric
    # jitter, matching elevation_changes) over raw cumulative distance
    # (already low-noise, not smoothed). np.diff shortens the array by one, so
    # a leading NaN pad keeps it aligned 1:1 with time_array/other columns.
    n = len(altitude) if altitude is not None else 0
    if n < 2 or distance is None or len(distance) < 2:
        return np.full(n, np.nan)

    smoothed = _smoothed_altitude(altitude, time_array, smooth_window_s)
    dist = np.asarray(distance, dtype=float)
    rise = np.diff(smoothed)
    run = np.diff(dist)

    with np.errstate(divide="ignore", invalid="ignore"):
        grade = np.where(run >= MIN_GRADE_RUN_M, rise / run * 100.0, np.nan)
    return np.concatenate([[np.nan], grade])


def climbing_time_s(
    grade: np.ndarray,
    time_array: np.ndarray,
    threshold_pct: float = CLIMBING_GRADE_THRESHOLD_PCT,
) -> float:
    if grade is None or len(grade) == 0:
        return 0.0
    mask = np.asarray(grade, dtype=float) > threshold_pct
    w = sample_weights(time_array)
    n = min(len(w), len(mask))
    return float(np.sum(w[:n][mask[:n]]))


def weighted_average(
    series: np.ndarray, time_array: np.ndarray, mask: Optional[np.ndarray] = None
) -> Optional[float]:
    if series is None or len(series) == 0:
        return None
    s = np.asarray(series, dtype=float)
    w = sample_weights(time_array)
    n = min(len(s), len(w))
    s, w = s[:n], w[:n]
    valid = ~np.isnan(s)
    if mask is not None:
        valid = valid & np.asarray(mask, dtype=bool)[:n]
    if not valid.any() or np.sum(w[valid]) == 0:
        return None
    return float(np.sum(s[valid] * w[valid]) / np.sum(w[valid]))


def normalized_power(power: np.ndarray, time_array: np.ndarray) -> Optional[float]:
    # Coggan Normalized Power formula: 30 s rolling average, 4th-power mean, 4th root.
    if power is None or len(power) == 0:
        return None
    p = np.nan_to_num(np.asarray(power, dtype=float), nan=0.0)
    window = max(1, int(round(30.0 / representative_dt(time_array))))
    if len(p) < window:
        return None
    rolling = np.convolve(p, np.ones(window) / window, mode="valid")
    return float(np.mean(rolling**4) ** 0.25)


def total_work_kj(power: np.ndarray, time_array: np.ndarray) -> Optional[float]:
    if power is None or len(power) == 0:
        return None
    p = np.nan_to_num(np.asarray(power, dtype=float), nan=0.0)
    w = sample_weights(time_array)
    n = min(len(p), len(w))
    return float(np.sum(p[:n] * w[:n]) / 1000.0)


# Recovery is only "passive" (and thus a meaningful HRR60 reading) if mean
# power over the 60s window stays below this fraction of FTP — matches the
# existing Z1 Active-Recovery/Z2 boundary (tools.py's _POWER_ZONES).
RECOVERY_MAX_FTP_FRAC = 0.55
# Fallback backoff threshold when FTP isn't known, relative to the interval's
# own average power.
RECOVERY_MAX_INTERVAL_FRAC = 0.5


def _window_mask(time_array: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return (time_array >= lo) & (time_array <= hi)


def _window_median(
    series: np.ndarray, time_array: np.ndarray, lo: float, hi: float
) -> Optional[float]:
    # Median, not weighted_average's mean — HR recovery within a short window is
    # non-linear, so a mean is skewed towards whichever end of the window has
    # more/faster-changing samples; the median is not.
    s = np.asarray(series, dtype=float)
    mask = _window_mask(time_array, lo, hi)
    n = min(len(s), len(mask))
    valid = mask[:n] & ~np.isnan(s[:n])
    if not valid.any():
        return None
    return float(np.median(s[:n][valid]))


def heart_rate_recovery_60s(
    hr: np.ndarray,
    power: np.ndarray,
    time_array: np.ndarray,
    end_s: float,
    next_start_s: Optional[float] = None,
    ftp: Optional[float] = None,
    interval_avg_power: Optional[float] = None,
) -> Optional[float]:
    if next_start_s is not None and next_start_s < end_s + 60:
        return None
    if time_array is None or len(time_array) == 0 or time_array[-1] < end_s + 60:
        return None

    threshold = None
    if ftp:
        threshold = RECOVERY_MAX_FTP_FRAC * ftp
    elif interval_avg_power:
        threshold = RECOVERY_MAX_INTERVAL_FRAC * interval_avg_power
    if threshold is not None:
        recovery_power = weighted_average(
            power, time_array, mask=_window_mask(time_array, end_s, end_s + 60)
        )
        if recovery_power is not None and recovery_power > threshold:
            return None

    end_hr = _window_median(hr, time_array, end_s - 5, end_s)
    recovery_hr = _window_median(hr, time_array, end_s + 57.5, end_s + 62.5)
    if end_hr is None or recovery_hr is None:
        return None
    return end_hr - recovery_hr
