---
title: Derive a moving mask algorithmically
status: ready   # see tasks/WORKFLOW.md for the lifecycle
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
- [ ] `time_summary()` counts a stop only for a not-moving run lasting at
      least `MIN_STOP_S = 10` seconds (a named module constant, measured
      with `sample_weights`, not sample counts). The mask itself is not
      filtered, so moving time and averages use the raw `speed > 0` mask.
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

## Test Plan

- `./check.sh` passes.
- New unit tests in `tests/test_activity_metrics.py`:
  - `moving_mask` with a speed column returns `speed > 0`;
  - a stray `"moving"` column is ignored (the mask follows speed);
  - no speed column → `None`; empty speed series → `None`;
  - NaN speed → not moving;
  - `time_summary` stop counting: a 5 s zero run is not counted, a 10 s
    and a 60 s zero run are; a stop at the very start of the activity is
    counted; with non-1 Hz sampling the threshold uses durations (e.g.
    zero runs at 2 s sampling).
- `tests/test_ai_tools.py`: `get_activity_details` on an activity with a
  speed column and a zero-speed stretch renders
  the `"Averages (moving | full):"` header and a stop count.
- Manual, on real data (read-only intervals.icu calls, no Anthropic API):
  for at least 20 recent activities across ride types, including an
  indoor one, `Σ sample_weights[moving_mask]` is within
  `max(30 s, 0.5%)` of intervals.icu `moving_time`. Record the worst case
  in Implementation Notes.
- Manual: run the `inspect_activity` dev script (at
  `scripts/inspect_activity.py` if 0013 is done, otherwise
  `src/data/inspect_activity.py`) on one outdoor ride with real stops and
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
