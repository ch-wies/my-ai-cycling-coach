---
title: Derive a moving mask algorithmically
status: draft   # see tasks/WORKFLOW.md for the lifecycle
release: v5     # see tasks/WORKFLOW.md; can be set before status: ready
---

## Problem / Context

`moving_mask()` (`src/analysis/activity_metrics.py:67-71`) reads a
per-sample `"moving"` boolean column and returns `None` when it's absent.
That column is never populated: `src/data/intervals_api.py:168-170`
explicitly notes intervals.icu doesn't expose a per-sample moving/stopped
stream. So `moving_mask()` unconditionally returns `None` today, for every
activity, which makes the `"Averages (moving | full):"` branch in
`_get_activity_details` (`src/ai/tools.py:333-355`) dead code in
production — not just for Temperature (added in story 0005), but for
Power, Heart rate, Speed, and Cadence too, which have had this same
dual-average code path for longer.

This is not an oversight. The module docstring
(`src/analysis/activity_metrics.py:12-15`) is explicit:

> "Moving" is taken from the data source's own `moving` boolean stream
> when present. We do not re-derive it from speed (GPS-only rides drift
> and would fool a threshold). If the source gives us no moving stream,
> moving-only stats are simply omitted rather than guessed.

That decision predates the intervals.icu migration — it was made in
`8c1b97c` ("Give the coach more tools to work with, fix dt calculation
bug"), back when the app synced from Strava and *did* have a real
`moving` stream available. Even then, a speed-threshold fallback was
deliberately rejected, citing GPS drift risk.

This story is about revisiting that decision: is there an algorithmic way
to derive a moving mask that avoids the GPS-drift failure mode the
docstring warns about, so the existing dual-average code (and anything
else gated on `moving_mask()`, e.g. `time_summary()`'s stop counting)
becomes reachable for real activities instead of permanently dead?

Three candidate directions were raised in initial discussion, not yet
evaluated or chosen:
- A distance-delta-over-a-window guard, mirroring `grade_series`'s
  `MIN_GRADE_RUN_M` pattern from story 0004 — averages out jitter instead
  of trusting an instantaneous speed sample.
- A smoothed-speed threshold with hysteresis (minimum-duration rule to
  avoid flicker at the boundary) — closer to the exact approach the
  docstring warns against, so would need to directly address why it's
  safe here when it wasn't judged safe before.
- A multi-signal guard combining speed with cadence/power, similar in
  spirit to `pedaling_mask`'s existing fallback chain.

Deliberately deferred to a later drafting session — this file currently
only records the problem, not the approach. See
[0005-temperature-readings.md](0005-temperature-readings.md) (where the
dead-code branch was first noticed) and
[0004-elevation-metrics.md](0004-elevation-metrics.md) (source of the
`MIN_GRADE_RUN_M` precedent).

## Acceptance Criteria

<!-- Checklist of concrete, verifiable outcomes. -->

- [ ]

## Technical Decisions

<!-- Code-related decisions made during drafting, with rationale. -->

## Test Plan

<!-- How to verify the implementation once done: manual steps and/or
     specific automated tests to add/run. -->

## Out of Scope

<!-- Explicit non-goals, to prevent scope creep during implementation. -->

## Implementation Notes

<!-- Filled in during/after implementation, not during drafting. What was
     actually built, especially where it deviates from Technical
     Decisions and why, plus any concrete results worth recording. -->
