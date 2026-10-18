---
title: Improve Aerobic decoupling interpretation
status: ready   # see tasks/WORKFLOW.md for the lifecycle
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
      "none" if there were no stops. This covers both stopped samples
      (moving mask false) and recording pauses (time gaps).
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
- **Stops:** a stop is the wall-clock gap between two consecutive moving
  samples that is larger than the gap threshold used by `sample_weights`
  (`max(GAP_FACTOR * median dt, MIN_GAP_SECONDS)`). Moving samples are
  those where `moving_mask` is true, or all samples if it returns `None`
  (consistent with `_moving_halves`). Working from the timestamps of moving
  samples catches both kinds of stop in one rule: stopped samples (moving
  mask false) and recording pauses (time gaps, which `sample_weights`
  hides). Stops before the first or after the last moving sample are
  ignored, since they don't fall between the halves.
  - Implemented as a small private helper in `src/ai/tools.py`, e.g.
    `_stops(time_array, mask) -> tuple[float, float]` returning total
    and longest stop in seconds.
  - Elapsed time for the percentage is first-to-last moving sample.
  - Minutes are rounded to whole minutes.
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
  > differs noticeably between the halves, either half has an elevated
  > Variability Index (roughly above 1.05, e.g. intervals, surges or
  > stop-and-go riding), or the ride includes a long stop (roughly 10+
  > minutes) or a large share of stopped time, treat decoupling as not
  > applicable and don't report it as a finding. Also use the splits to
  > judge whether the athlete faded, paced evenly, or negative-split the
  > effort.

  The ~1.05 VI and ~10 min stop values are rules of thumb for the coach,
  not thresholds applied in code. 10 min was chosen over 5 min because
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
- Stops, using an activity with timestamps and a `moving` stream:
  - No stops: output contains `Stopped time: none`.
  - Several short stops vs one long stop with the same total: both report
    the same total, but the longest stop differs (short vs long).
  - A recording pause (time gap with no samples) is counted as a stop,
    the same as a run of samples with `moving` false.
  - `_stops` unit tests for the helper directly (total and longest in
    seconds; leading/trailing stops ignored).
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
- Changing the moving mask or the half-split logic (`_moving_halves`).
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
