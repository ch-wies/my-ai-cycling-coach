---
title: Improve Aerobic decoupling interpretation
status: done   # see tasks/WORKFLOW.md for the lifecycle
release: v5     # see tasks/WORKFLOW.md; can be set before status: ready
---

## Problem / Context

The coach often flags aerobic decoupling when it isn't meaningful. The
usual cause is a session that wasn't ridden at even power. Pw:Hr
decoupling compares the power:HR ratio of the first and second halves of
moving time, and it is only valid for steady efforts.

`get_activity_efficiency` (`src/ai/tools.py`) already returns the average
power per half next to the decoupling number, but the coach still
over-flags. Two gaps cause this:

1. The tool description presents decoupling as a general durability
   metric. Nothing tells the coach that it only applies to steady efforts.
2. Average power per half only shows unevenness *between* the halves. It
   misses unevenness *within* a half, such as surges, intervals or
   stop-and-go riding. Two halves can both average 200 W while one is
   steady and the other is a set of hard intervals. Average HR per half is
   also not shown (only the W/bpm ratio is), so the coach can't tell
   whether power or HR is what moved.
3. Stops are invisible to the coach. Short stops (traffic lights) don't
   matter, because HR is back on track within a minute or two. A long stop
   (e.g. a café stop) partly resets the drift mechanisms (core
   temperature, cardiovascular state), so the ride is no longer one
   continuous effort and decoupling stops making sense. The longest single
   stop matters more than the total: ten 1-minute stops barely affect
   decoupling, one 15-minute stop does.

This story gives the coach the numbers it needs to judge whether a session
was steady, and tells it in the tool description to make that judgement
before using decoupling. The coach decides; the code does not enforce a
cut-off.

This is separate from 0011 and 0012, which look at replacing the standard
half-split decoupling calculation itself. This story keeps the current
calculation and only changes what is reported next to it and how it is
described.

## Acceptance Criteria

- [ ] The "Splits (first half | second half)" block of
      `get_activity_efficiency` output additionally reports, per half:
      Normalized Power, Variability Index (NP / average power), and average
      heart rate.
- [ ] The output reports stops: total stopped time (minutes and % of
      elapsed time) and the duration of the longest single stop, or
      "none" if there were no stops. Stops come only from the shared
      `stop_durations()` helper from 0008, which covers mask-false
      stretches and recording gaps, each at least `MIN_STOP_S`. Stops
      before the first or after the last moving sample are ignored.
- [ ] If `moving_mask()` returns `None` (no speed stream), the line reads
      `Stopped time: unavailable (no speed stream)`.
- [ ] The existing output is unchanged otherwise: the decoupling line,
      the average power split and the speed split keep their current
      format, so existing tests pass unmodified.
- [ ] Each new line appears only when its inputs are available (NP/VI need
      power and enough samples in both halves for NP's 30 s window; HR
      needs heart rate). A missing value never breaks the rest of the
      output.
- [ ] The `get_activity_efficiency` tool description states that
      decoupling is only meaningful for steady efforts. It tells the coach
      to check the half splits (average power, NP, VI) and stops first,
      and to treat decoupling as not applicable, rather than reporting it
      as a finding, when the session was not evenly paced or not
      continuous (long stop).
- [ ] No code-side gate: the decoupling number is still always computed
      and returned when power and HR exist. The decision is left to the
      coach.

## Technical Decisions

- **Where:** all changes are in `src/ai/tools.py`: the
  `get_activity_efficiency` entry in `TOOLS` (description) and
  `_get_activity_efficiency` (output). No changes to `src/analysis/`.
- **Depends on 0008.** The moving mask (`speed > 0`) and
  `stop_durations()` are the single source of truth for moving and
  stopped. This story adds no moving or stop logic of its own. Without
  0008 the mask is always `None` and the stops line would always read
  unavailable.
- **NP per half:** reuse `normalized_power(power, time_array)` from
  `src/analysis/activity_metrics.py`, called on the half's samples:
  `normalized_power(power[h], time_array[h])` for each half mask `h` from
  `_moving_halves`. This drops stopped samples, consistent with the
  existing per-half averages, which also use the moving-mask halves.
  `representative_dt` uses the median sample spacing, so the gaps left by
  dropped stops don't change the 30 s window size. If `normalized_power`
  returns `None` for either half (too few samples), the NP and VI lines
  are omitted.
- **VI per half:** `NP / average power` of the same half, using the
  existing `weighted_average` power values (`p1`, `p2`). Formatted to two
  decimals, matching the activity-level VI in `get_activity_details`.
  Omitted if average power is missing or zero.
- **HR per half:** `weighted_average(hr, time_array, h)` (the same values
  already computed for decoupling), formatted as whole bpm.
- **Stops:** use `stop_durations(time_array, mask)` from 0008, so the stop
  definition (mask-false stretches plus recording gaps, at least
  `MIN_STOP_S`) is identical to the stop count in `get_activity_details`.
  - Leading and trailing stops are dropped by passing only the slice from
    the first to the last moving sample (`time_array[i:j+1]`,
    `mask[i:j+1]`). Then no stop can touch the edges, and the helper needs
    no edge parameter. Such stops don't split the effort: standing still
    before rolling off or after finishing shouldn't make the coach
    discard decoupling.
  - Total = sum of the durations; longest = their maximum.
  - Elapsed time for the percentage is the wall-clock span of that same
    slice (first to last moving sample).
  - Minutes are rounded to whole minutes.
  - `mask is None` → `Stopped time: unavailable (no speed stream)`. The
    halves still treat every sample as moving (unchanged
    `_moving_halves`), but stops can't be checked, and saying "none"
    would claim a check that didn't happen.
- **Output format:** the stops line goes after the decoupling line, before
  the splits block. The new per-half lines go in the existing splits
  block, after the `Power` line and before `Speed`:
  ```
    Aerobic decoupling (Pw:Hr): +3.2% (first half 1.43 → second half 1.38 W/bpm)
    Stopped time: 12 min (8% of elapsed), longest stop 9 min
    Splits (first half | second half):
      Power: 200 W | 195 W
      Normalized Power: 210 W | 240 W
      Variability Index: 1.05 | 1.23
      Heart rate: 140 bpm | 147 bpm
      Speed: 30.1 km/h | 29.4 km/h
  ```
  With no stops: `Stopped time: none`. The line is always shown, so the
  coach knows stops were checked.
- **Tool description:** replace the current text with wording along these
  lines (final phrasing can be tuned during implementation):
  > Assess pacing and aerobic durability for a specific activity: aerobic
  > decoupling (Pw:Hr drift between the first and second half of moving
  > time), stopped time, and first-half vs second-half splits of average
  > power, Normalized Power, Variability Index, heart rate and speed.
  > Decoupling is only meaningful for steady, continuous, evenly paced
  > efforts. Before using it, check the splits and stops: if average power
  > differs by more than ~7% between the halves, either half has an elevated
  > Variability Index (roughly above 1.15, e.g. intervals, surges or
  > stop-and-go riding), or the ride includes a long stop (roughly 10+
  > minutes) or a large share of stopped time, treat decoupling as not
  > applicable and don't report it as a finding. Also use the splits to
  > judge whether the athlete faded, paced evenly, or negative-split the
  > effort.

  The ~7% power split, ~1.15 VI and ~10 min stop values are rules of thumb
  for the coach, not thresholds applied in code.

  The VI value was raised from an initial ~1.05 during implementation.
  Real steady rides sit around 1.05–1.15: a road endurance ride at
  1.14 | 1.11 and an indoor ride at 1.07 | 1.11. At 1.05 the coach would
  have discarded decoupling on almost every ride. The power split and the
  stop checks catch most invalid sessions anyway, and intervals, group
  rides and stop-and-go riding usually exceed 1.2, so 1.15 still catches
  within-half unevenness.

  ~7% for the power split is deliberately lenient. An uneven split skews
  decoupling by itself, because HR doesn't drop in proportion to power. A
  7% lower second half can show roughly 3–4% decoupling without real
  drift. That is accepted, since the coach sees the power split next to
  the number.

  10 min was chosen over 5 min because
  shorter stops mainly cause a brief HR lag on restart, while the drift
  mechanisms (core temperature, cardiovascular state) need roughly 10–20
  min to meaningfully recover.

## Test Plan

Automated, in `TestGetActivityEfficiency` in `tests/test_ai_tools.py`
(using the existing `_real_activity` helper):

- Constant power and HR: output contains the `Normalized Power`,
  `Variability Index` (`1.00 | 1.00`) and `Heart rate` lines with equal
  values for both halves.
- Steady first half, variable second half (e.g. alternating high/low power
  blocks with the same average): the average power split is equal, but the
  second half's NP and VI are clearly higher than the first's. This checks
  that the new lines catch within-half unevenness.
- HR missing: the decoupling line still shows "needs both power and heart
  rate", the NP/VI lines are present, and there is no `Heart rate` line.
- Stops, using an activity with timestamps and a `speed` stream, with
  stops expressed as zero-speed stretches (0008's convention):
  - No stops: output contains `Stopped time: none`.
  - Several short stops vs one long stop with the same total: both report
    the same total, but the longest stop differs (short vs long).
  - A recording pause (time gap with no samples) is counted as a stop,
    the same as a zero-speed stretch.
  - A zero-speed run shorter than `MIN_STOP_S` is not reported.
  - Zero-speed stretches at the very start and end are ignored: an
    activity whose only stops are at the edges reports
    `Stopped time: none`.
  - No speed column: output contains
    `Stopped time: unavailable (no speed stream)`, and the rest of the
    output is still rendered.
  - The stop definition itself (`stop_durations`) is unit-tested in 0008
    and isn't retested here.
- Existing efficiency tests pass unchanged (format of the existing lines is
  preserved).
- Test asserting the `get_activity_efficiency` description in `TOOLS`
  mentions that decoupling only applies to steady efforts (e.g. contains
  "Variability Index", "stop" and "not applicable").

Manual (needs Anthropic API calls, run by the user):

- In the Training tab chat, ask the coach about a recent unevenly paced
  ride (intervals or group ride) and a recent steady endurance ride. For
  the uneven ride the coach should call decoupling not applicable; for the
  steady ride it should still discuss it. If available, also try a ride
  with a long café stop: the coach should call decoupling not applicable.

## Out of Scope

- Changing how decoupling itself is calculated (half-split, Pw:Hr ratio),
  and any code-side validity gate. That is the subject of 0011 and 0012.
- Changing the moving mask, the stop definition (`stop_durations`,
  `MIN_STOP_S`; both owned by 0008) or the half-split logic
  (`_moving_halves`).
  Stopped samples stay excluded from the per-half numbers; long stops are
  surfaced through the stops line instead.
- Changes to the coach's system prompt. The guidance lives in the tool
  description, next to the data it refers to.
- Adding the per-half metrics to other tools (e.g.
  `get_activity_intervals`).

## Implementation Notes

<!-- Filled in during/after implementation, not during drafting. What was
     actually built, especially where it deviates from Technical
     Decisions and why, plus any concrete results worth recording. -->

Implemented as drafted, except for the description's rules of thumb (see
the deviation below).

- `src/ai/tools.py` only:
  - The new `get_activity_efficiency` description, with the drafted
    wording.
  - A new `_stops_line(time_array, mask)`. It slices to the first..last
    moving sample, calls `stop_durations()`, and formats total, % of that
    span and longest stop. It returns `none` or `unavailable (no speed
    stream)` where those apply.
  - In `_get_activity_efficiency`, the stops line comes after the
    decoupling line. The NP, VI and HR split lines sit between Power and
    Speed, each shown only when its inputs exist.
- Small addition: the early return is now `if h1 is None or h2 is None:`
  (previously `h1` only). `_moving_halves` returns both or neither, but
  mypy can't narrow `h2` from the `h1` check, and the NP slicing indexes
  with `h2`.
- `tests/test_ai_tools.py`: `_real_activity` gains an optional `times=`
  argument for recording-gap tests. There are 10 new
  `TestGetActivityEfficiency` tests (Test Plan items), and the existing
  efficiency tests are unchanged.

Verification:
- `./check.sh`: all pass (361 tests).
- Real data via `python -m scripts.inspect_activity` (read-only):
  - i190844156 (road): `Stopped time: 40 min (20% of elapsed), longest
    stop 24 min`, NP 225 | 211 W, VI 1.14 | 1.11, HR 126 | 130 bpm.
  - i161860086 (VirtualRide): `Stopped time: none`, VI 1.07 | 1.11.
  - i181946205 (gravel, no power): stops only, and the decoupling "needs
    both" line, without errors.
- Deviation from the drafted description: real rides, even indoor ones,
  showed a VI above the drafted ~1.05. The VI rule of thumb was therefore
  raised to ~1.15, and "differs noticeably" for the power split was made
  concrete as ~7%. See Technical Decisions for the reasoning.
- Manual coach check (Test Plan; run by the user against the Anthropic API):
  - Manually checked both, v4 and current codebase. For the activity from August 22, the coach from v4 flagged decoupling as worrysome and the new coach puts the numbers into perspective explaining the uneven pacing. So test passed.
