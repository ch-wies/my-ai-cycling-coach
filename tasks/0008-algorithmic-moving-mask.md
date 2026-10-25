---
title: Derive a moving mask algorithmically
status: done   # see tasks/WORKFLOW.md for the lifecycle
release: v5     # see tasks/WORKFLOW.md; can be set before status: ready
---

## Problem / Context

`moving_mask()` (`src/analysis/activity_metrics.py:67-71`) reads a
per-sample `"moving"` boolean column and returns `None` when it's absent.
That column is never populated: `src/data/intervals_api.py:177-179`
explicitly notes intervals.icu doesn't expose a per-sample moving/stopped
stream. So `moving_mask()` unconditionally returns `None` today, for every
activity, which makes the `"Averages (moving | full):"` branch in
`_get_activity_details` (`src/ai/tools.py`) dead code in production — not
just for Temperature (added in story 0005), but for Power, Heart rate,
Speed, and Cadence too. The same goes for every other consumer of the mask:
`time_summary()`'s stop counting, the moving-only average power in the
training-load tool, and `_moving_halves` in the efficiency/decoupling tool.

This is not an oversight. The module docstring
(`src/analysis/activity_metrics.py:12-15`) is explicit:

> "Moving" is taken from the data source's own `moving` boolean stream
> when present. We do not re-derive it from speed (GPS-only rides drift
> and would fool a threshold). If the source gives us no moving stream,
> moving-only stats are simply omitted rather than guessed.

That decision predates the intervals.icu migration — it was made in
`8c1b97c` back when the app synced from Strava and *did* have a real
`moving` stream.

### Finding: speed is already zeroed when stopped

During drafting, a hand-labelled ground-truth bench was planned (drafted as
[0016](0016-shared-analysis-bench.md), now cancelled). Neither intervals.icu
nor Garmin FIT files provide a per-sample moving stream: FIT only carries
auto-pause timer events, which already surface as gaps in the time stream
and are absent on rides recorded without auto-pause.

Before building the bench, the intervals.icu `velocity_smooth` stream
(mapped to `speed`) was checked directly, read-only, on 42 activities from
2025-11 to 2026-10:

- Devices: Garmin Edge 850, Edge 1030 Plus (these are ICTrainer intoor rides), Edge Explore.
- Types: Ride (with speed sensor), GravelRide, MountainBikeRide (without speed sensor), VirtualRide (indoor).
- The devices record straight through stops: `icu_recording_time` ≈
  `elapsed_time`, and `recording_stops` is almost always empty. Stops
  therefore sit *inside* the stream.
- While stopped, speed is **exactly `0.0`**, with no GPS jitter. The
  smallest non-zero speed is 0.03–0.20 m/s.
- `Σ sample_weights[speed > 0]` vs intervals.icu `moving_time`:
  MTB/Gravel/Virtual rides match within 0–2 s; road rides are +1 to +21 s
  over 1–11.6 h rides. Long stops match too (e.g. 18,502 s stopped on a
  gravel ride, 2,971 s on an MTB ride).
- Indoor/VirtualRide speed is always > 0, so indoor rides come out as fully
  moving with no special case.
- No NaNs in `speed` on any sampled ride.
- Zero-speed runs of ≤ 2 s are common (5–25% of all zero runs per ride,
  e.g. 19 of 82 on one gravel ride): track stands, slow hairpins, brief
  dropouts.

So the GPS-drift failure mode behind the original decision does not occur
with this data source: the recording device has already done the stop
detection. `speed > 0` is the moving mask.

Caveats, accepted:
- Agreement with `moving_time` is partly circular, since intervals.icu very
  likely computes it from the same stream. It shows we match intervals.icu's
  (and Garmin's) definition, which is also the moving time the coach
  already sees in the metadata, rather than an independent ground truth.
- All checked rides are Garmin recordings. Another source (Wahoo, Zwift
  direct, manual upload) might not zero speed when stopped; this is
  revisited only if such data shows up.

### Behaviour change for the coach

Once the mask is live, these previously dead paths become active for
every activity with a speed stream:
- Dual "moving | full" averages in `get_activity_details`.
- A stop count in the Time section.
- Moving-only average power in the training-load tool.
- Moving-time halves in the efficiency/decoupling tool.

Stories 0011/0012 (decoupling) build on that last one.

## Acceptance Criteria

- [ ] `moving_mask(activity)` returns `speed > 0` as a boolean array
      aligned 1:1 with the time array, or `None` when there is no or an
      empty speed stream. It no longer reads a `"moving"` column at all.
- [ ] The `"moving"` exclusion in `Activity.available_metrics`
      (`src/data/activity.py:80`) and its comment are removed (nothing
      produces that column any more).
- [ ] A public helper `stop_durations(time_array, mask) -> list[float]` in
      `src/analysis/activity_metrics.py` returns the duration in seconds of
      every stop, in time order. This is the single stop definition, also
      used by 0015. A stop is a contiguous stretch of not-moving time
      lasting at least `MIN_STOP_S = 10` seconds (a named module constant).
      Not-moving time is:
      - mask-false samples, measured with `sample_weights` (durations, not
        sample counts), and
      - recording gaps (time deltas above the `sample_weights` gap
        threshold), counted as the part of the delta that `sample_weights`
        does not assign to a sample (delta − median dt).
      A gap next to a mask-false run, or between two of them, merges into
      one stop. Leading and trailing stops are included.
- [ ] `time_summary()`'s `stops` count is the number of entries from
      `stop_durations()`. The mask itself is not filtered, so moving time
      and averages use the raw `speed > 0` mask.
- [ ] `time_summary()` keeps preferring metadata `total_moving_time` for
      `moving_s` when present (unchanged).
- [ ] The module docstring of `src/analysis/activity_metrics.py` and the
      comment in `src/data/intervals_api.py` are updated to the new
      rationale: speed is derived because the recording device already
      zeroes it when stopped, verified against intervals.icu `moving_time`.
- [ ] The "Moving: unavailable (no moving stream from data source)" wording
      in `src/ai/tools.py` is checked: it only appears when there is
      neither metadata moving time nor a mask, and its text is adjusted if
      it no longer describes that case.
- [ ] Existing tests that inject a `"moving"` column
      (`tests/test_activity_metrics.py` `TestTimeSummary`, the
      `tests/test_ai_tools.py` activity helper's `moving=` argument) are
      rewritten to express stops as zero-speed stretches. New unit tests
      (see Test Plan) pass.
- [ ] `./check.sh` passes.

## Technical Decisions

- **Derive in `moving_mask()` (analysis layer), not as a precomputed column
  in the data layer.** The `grade` precedent precomputes in
  `intervals_api.py` so the UI plot dropdown and the AI tools see the same
  column. `moving` is explicitly excluded from plottable series
  (`src/data/activity.py:80`, an exclusion this story removes), and every
  consumer already goes through `moving_mask()`, so a single derivation
  point there is enough.
- **No source-provided `"moving"` column.** The column existed only for
  Strava's moving stream; nothing produces it now. Accepting one would let
  a future source pass in a mask computed under a different definition,
  making moving stats inconsistent across activities. With only our own
  derivation there is one code path and one definition.
- **Rule: `speed > 0`, no smoothing, no hysteresis, no distance-window
  guard.** The three candidate directions from initial discussion
  (distance-delta window, smoothed threshold with hysteresis, multi-signal
  guard with cadence/power) all solve GPS jitter, which the data doesn't
  have. Any of them would also make moving time drift from intervals.icu's
  figure.
- **`NaN` speed counts as not moving** (`nan > 0` is `False`). No NaNs were
  observed, so this is a defined edge case rather than a tuned choice.
- **No speed stream → `None`**, not a cadence/power fallback: pedalling ≠
  moving (coasting would count as stopped outdoors), and indoor rides
  without virtual speed lose nothing because everything is moving anyway.
- **Minimum stop duration applies to stop counting only**
  (`MIN_STOP_S = 10`). Filtering short zero runs out of the mask itself
  would make moving time diverge from intervals.icu for no gain. 10 s is
  a judgement call (a track stand or slow hairpin isn't a "stop"); it's a
  named constant so it can be revisited.
- **Recording gaps count as stops.** `time_summary()`'s `stopped_s`
  (elapsed − moving) already treats pause time as stopped, so the stop
  count should agree with it. On a ride recorded with auto-pause, a café
  stop shows up only as a gap. `sample_weights` deliberately hides gaps
  from moving time, so `stop_durations()` adds them back explicitly.
- **One shared stop helper.** `stop_durations()` is public so 0015
  (stopped time and longest stop in the efficiency tool) uses the same
  definition, and the Time section and the efficiency tool never disagree.
  It returns durations rather than a count so callers can take a count,
  a total or a maximum. It takes the mask as a non-optional argument;
  callers decide what a missing mask means.

## Test Plan

- `./check.sh` passes.
- New unit tests in `tests/test_activity_metrics.py`:
  - `moving_mask` with a speed column returns `speed > 0`;
  - a stray `"moving"` column is ignored (the mask follows speed);
  - no speed column → `None`; empty speed series → `None`;
  - NaN speed → not moving;
  - `stop_durations`: a 5 s zero run is not counted, a 10 s and a 60 s
    zero run are, with the right durations; a stop at the very start or
    end of the activity is included; with non-1 Hz sampling the threshold
    uses durations (e.g. zero runs at 2 s sampling).
  - `stop_durations` with gaps: a 30 s recording gap between moving
    samples is one stop of ~30 s; a 7 s gap (above the 5 s gap threshold
    but below `MIN_STOP_S`) is not counted; a 6 s zero run followed by a
    6 s gap merges into one stop of ~12 s.
  - `time_summary`'s `stops` equals `len(stop_durations(...))` on an
    activity with zero runs and a gap.
- `tests/test_ai_tools.py`: `get_activity_details` on an activity with a
  speed column and a zero-speed stretch renders
  the `"Averages (moving | full):"` header and a stop count.
- Manual, on real data (read-only intervals.icu calls, no Anthropic API):
  for at least 20 recent activities across ride types, including an
  indoor one, `Σ sample_weights[moving_mask]` is within
  `max(30 s, 0.5%)` of intervals.icu `moving_time`. Record the worst case
  in Implementation Notes.
- Manual: run the `inspect_activity` dev script
  (`scripts/inspect_activity.py`; 0013 is implemented first) on one
  outdoor ride with real stops and
  one indoor ride. Check the tool output shows plausible moving | full
  averages, a stop count, and (indoor) no stops.

## Out of Scope

- A hand-labelled moving/stopped bench. Drafted as 0016 and cancelled after
  the speed-stream finding; revive 0016 if a non-Garmin source or a new
  task needs per-sample ground truth.
- Handling sources that don't zero speed when stopped (no such data today).
- Using the mask for anything beyond its existing consumers (e.g. the UI
  plots, or `coasting_time` from metadata).
- Revisiting the decoupling interpretation on top of the now-active moving
  halves; that belongs to 0011/0012/0015.

## Implementation Notes

<!-- Filled in during/after implementation, not during drafting. What was
     actually built, especially where it deviates from Technical
     Decisions and why, plus any concrete results worth recording. -->

Implemented as drafted.

- `moving_mask()` returns `speed > 0` (float cast, so NaN → not moving),
  or `None` for a missing or empty speed stream.
- `MIN_STOP_S = 10.0` and the public `stop_durations(time_array, mask)` are
  in `src/analysis/activity_metrics.py` (also exported from
  `src.analysis`). `stop_durations` is a single pass over the samples:
  - a gap before sample `i` adds `delta − median dt`;
  - a mask-false sample adds its `sample_weights` weight;
  - a moving sample closes the current stop, which is kept if it is
    ≥ `MIN_STOP_S`.

  This merges gaps with adjacent zero-speed runs and keeps leading and
  trailing stops. The gap threshold formula is factored into
  `_gap_threshold()` so that `sample_weights` and `stop_durations` can't
  drift apart.
- `time_summary()`: `stops = len(stop_durations(...))`, and `_count_stops`
  is removed. Moving-time logic is unchanged.
- `Activity.available_metrics`' `"moving"` exclusion is removed, and the
  module docstring and the `intervals_api.py` comment are rewritten.
- `tools.py`: the fallback now reads
  `Moving: unavailable (no moving time or speed stream)`, since that is the
  only case where it can still appear.
- Tests: `TestMovingMask`, `TestStopDurations` and the rewritten
  `TestTimeSummary` in `tests/test_activity_metrics.py`. In
  `tests/test_ai_tools.py`, `_real_activity` loses its `moving=` argument,
  the no-speed and dual-averages tests are adapted, and a new zero-speed
  stop test was added.

Verification:
- `./check.sh`: all pass (351 tests).
- Moving time vs intervals.icu `moving_time` (read-only, throwaway script):
  45 recent outdoor activities (Ride, GravelRide, MountainBikeRide;
  25 min–11.6 h) plus 5 VirtualRides. All 50 are within
  `max(30 s, 0.5%)`, most match exactly. Worst case relative to tolerance:
  i161859892 (MTB) +20 s against 30 s. Largest absolute difference:
  i174129337 −26 s on a 4.9 h ride (tolerance 87 s). VirtualRides are
  0 to +1 s, and four of the five show 0 stops.
- Stop counts on real data are plausible. Road rides have 0–19 stops;
  gravel and MTB have 40–95 stops (frequent short stops of 10 s or more)
  with long stops recovered, e.g. 9,879 s on i181946205.
- `python -m scripts.inspect_activity i190844156` (outdoor):
  `Stopped: 40m14s (11 stops)`, and `Averages (moving | full)` with moving
  values above full (Power 194 | 155 W, Speed 30.3 | 24.3 km/h).
  i161860086 (VirtualRide): moving = elapsed, no stop count, equal
  averages.
