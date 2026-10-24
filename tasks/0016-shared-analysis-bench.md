---
title: Generalise the interval-detection bench into a shared analysis bench
status: cancelled   # see tasks/WORKFLOW.md for the lifecycle
release: # see tasks/WORKFLOW.md; can be set before status: ready
---

## Problem / Context

Cancelled: not needed for 0008. intervals.icu speed is already exactly 0 when stopped, so `speed > 0` matches `moving_time` without hand-labelled ground truth (see 0008). Kept for revival if a future task needs a shared labelling bench.

Story [0008](0008-algorithmic-moving-mask.md) (derive a moving mask
algorithmically) has no way to measure candidate algorithms: there is no
ground truth for "moving vs stopped". Neither intervals.icu nor Garmin FIT
files provide a per-sample moving stream (FIT only has timer start/stop
events for auto-pause, which already surface as gaps in the time stream and
are missing entirely on rides without auto-pause). So ground truth has to be
**hand-labelled stop segments**.

The repo already has a labelling + evaluation bench, but it lives inside the
`interval_detection` package (`interval_detection/bench/`) and is specific to
that task:

- `label_tool.py` (pyqtgraph) only loads and plots `t,power`; stops need
  speed, cadence and power on a shared time axis.
- `labelio.py` hardcodes the interval tag vocabulary (`INTERVAL_TYPES`), the
  `intervals` label key and the bench paths.
- `activities/*.csv` store only `t,power` (25 activities, 1.6 MB).
- `evaluate.py` / `view_results.py` are interval-specific (coverage
  matching, FTP threshold overlay) and stay that way.

The core of the label tool — draggable tagged time regions, activity
navigation, autosave, the `null` (unlabelled) vs `[]` (labelled, nothing
found) distinction — is task-agnostic.

The bench was originally put inside the package so it could travel with it
if `interval_detection` were extracted into its own repo (the expectation
being that detection might need heavier ML tooling). Detector v1 turned out
to be a simple rule-based algorithm, so that argument has weakened. The
**detector package itself stays pure and independent** (cheap to keep:
pyproject + `-e ./interval_detection`); only the bench moves out of it into
an app-level shared bench.

A shared corpus of full-stream activities is also useful beyond 0008 —
e.g. decoupling (0011/0012), grade (0004) or temperature (0005) work could
add their own label sets against the same activities.

**Depends on [0013](0013-scripts-and-scratch-folders.md)**, which moves
`export_for_bench.py` to `scripts/`. This story edits it at that new
location.

## Acceptance Criteria

- [ ] New top-level `bench/` exists with the layout from Technical
      Decisions; `interval_detection/bench/` no longer exists.
- [ ] `bench/label_tool.py --task <name>` opens the label tool for any
      configured task, plotting that task's channels on stacked plots with
      a linked time axis and offering that task's tag vocabulary (no tag
      combo when the vocabulary is empty).
- [ ] `--task intervals` behaves as the old tool did: power trace with the
      optional 20 s smoothing, intensity-ordered type combo, the same
      keyboard controls, autosave on navigation.
- [ ] `--task moving` opens with speed, cadence and power channels and a
      single `stopped` tag. It is usable on any corpus activity seeded for
      that task (no moving labels are created in this story).
- [ ] The 25 interval activities in `bench/activities/` are re-exported
      with full streams (no GPS), and their `t` and `power` columns are
      verified identical to the pre-migration CSVs.
- [ ] Interval label files are relocated to `bench/tasks/intervals/labels/`
      with `git mv`, byte-identical (no content change in `git diff -M`).
- [ ] `python bench/tasks/intervals/evaluate.py` output is identical to the
      output of `python interval_detection/bench/evaluate.py` captured just
      before the migration (last recorded: P 91.5% / R 81.2% / F1 86.1%,
      6 FP, boundary median 5.7 s, FTP 325, 24 labelled activities).
- [ ] `bench/tasks/intervals/view_results.py` works as before.
- [ ] `python -m scripts.export_for_bench --task <name> <id> [...]` writes
      the full-stream CSV to `bench/activities/` and seeds meta only in the
      named task's label directory, without touching existing labels.
- [ ] The `[bench]` extra is removed from `interval_detection/pyproject.toml`;
      matplotlib is declared directly in `requirements-dev.in`, and
      `requirements-dev.txt` is regenerated with pip-compile.
- [ ] The bench tests (`test_bench_io.py`, `test_evaluate.py`,
      `test_view_results.py`) move from `interval_detection/tests/` to
      `tests/bench/` and pass; new tests cover the generic IO (see Test
      Plan).
- [ ] `bench/README.md` documents the layout, how to add a task, and how
      to run the tool, export and evaluation. README.md and CLAUDE.md
      Project Structure mention `bench/`.
- [ ] `./check.sh` passes.

## Technical Decisions

- **Layout:**
  ```
  bench/
    README.md
    label_tool.py            # generic, --task <name>
    labelio.py               # generic IO, parameterised by task config
    tasks.py                 # task registry (TaskConfig per task)
    activities/<id>.csv      # shared full-stream corpus (no GPS)
    tasks/
      intervals/  labels/, evaluate.py, view_results.py
      moving/     labels/    # evaluate.py comes with 0008
  ```
- **Task config:** a typed `TaskConfig` (NamedTuple/dataclass) registered in
  `bench/tasks.py` with: `name`, `channels` (plotted columns, in order),
  `tags` (vocabulary, ordered; may be empty), `default_tag`, `label_key`
  (JSON key holding the regions), `labels_dir`, `required_channels`
  (export refuses activities missing them). Configs:
  - `intervals`: channels `power`; tags = current `INTERVAL_TYPES` in the
    same order, default `other`; label key `intervals`; required `power`.
  - `moving`: channels `speed`, `cadence`, `power`; tags `stopped`;
    label key `stops`; required `speed`.
- **Label key per task**, so the existing interval label files keep their
  `intervals` key and stay byte-identical. Region entries keep the current
  `{"start_s", "end_s", "type"}` shape for every task.
- **Activity meta (`indoor`, `sport_type`) stays in each task's label
  files**, seeded at export, as now. It is duplicated across tasks when an
  activity is in more than one; that is accepted to keep interval labels
  untouched.
- **The tool's activity list for a task = the label files in that task's
  `labels_dir`** (not every corpus CSV), so moving-only rides don't show up
  in the intervals tool and vice versa. All 25 current interval activities
  already have a (seeded) label file, so the interval list is unchanged.
- **Label files are moved with `git mv`, never rewritten** (labels only
  change through the label tool).
- **Corpus format:** CSV, one file per activity, the streams as mapped by
  `src/data/intervals_api.py` (`t`, `distance`, `speed`, `cadence`,
  `power`, `heart_rate`, `altitude`, `temperature`, derived `grade`);
  columns present only when the activity has them. No GPS coordinates
  (the repo is on GitHub; start/end points would reveal home location).
  `labelio` loads a CSV as a column dict, and a task reads only the
  channels it needs.
- **Export (`scripts/export_for_bench.py`, after 0013):** takes a
  required `--task`. It checks `required_channels`, writes the shared CSV
  (overwriting is safe because the corpus is task-independent) and seeds
  meta via `save_meta` in that task's label dir only.
- **Migration safety:** a one-off migration step (run during
  implementation, not kept as a script) re-exports the 25 interval
  activities and compares `t,power` to the old CSVs. Any mismatch stops
  the migration so labels never misalign silently.
- **The detector package stays pure:** `bench/` may import
  `interval_detection`, never the reverse. `interval_detection/` keeps the
  detector, its unit tests and its pyproject, minus the `[bench]` extra.
- **Bench scripts keep the existing `sys.path` shim pattern** for importing
  `labelio` / `tasks` from `bench/`, since `bench/` is run as scripts and
  not installed. `tests/bench/` imports them the same way as the current
  bench tests.

## Test Plan

- `./check.sh` passes (ruff check, ruff format --check, mypy, pytest).
- Moved tests (`tests/bench/test_bench_io.py`, `test_evaluate.py`,
  `test_view_results.py`) pass against the new paths.
- New unit tests in `tests/bench/`:
  - loading a multi-column CSV returns every present column, and a missing
    column is absent, not filled;
  - save/load round trip with a non-default `label_key` (`stops`), keeping
    the `null` vs `[]` distinction;
  - `save_meta` seeds only the given task's label dir;
  - a tag outside the task vocabulary is coerced to the task's
    `default_tag`;
  - an empty-vocabulary task round-trips regions;
  - export refuses an activity missing a required channel.
- Migration: the `t,power` identity check passes for all 25 activities, and
  `git diff -M --stat` shows the label files as pure renames (100%
  similarity).
- Capture `python interval_detection/bench/evaluate.py` output before the
  migration, then diff it against `python bench/tasks/intervals/evaluate.py`
  afterwards. They must be identical.
- Manual: `python bench/label_tool.py --task intervals` opens one of the
  25 activities with its existing intervals and types, and editing,
  navigating and saving all work.
- Manual: export one outdoor ride with stops via
  `python -m scripts.export_for_bench --task moving <id>`, then
  `python bench/label_tool.py --task moving` shows the speed, cadence and
  power plots linked in time. Add a `stopped` region, save, and confirm
  `bench/tasks/moving/labels/<id>.json` contains it under `stops`. That
  test label is not committed (deleting it is part of the manual test).
- Manual: `python bench/tasks/intervals/view_results.py` opens and arrow-key
  navigation works.

## Out of Scope

- Folding `interval_detection` into `src/analysis/` (the package stays
  independent).
- Any change to the interval detector algorithm or its evaluation metric.
- Moving-mask evaluation (`bench/tasks/moving/evaluate.py`), activity
  selection and labelling for the moving task — that is story 0008.
- A shared corpus-level meta file (meta stays per task, see Technical
  Decisions).
- Storing or plotting GPS coordinates.
- Switching the corpus to parquet or adding git-lfs/DVC (1.6 MB today; a
  full-stream corpus of a few dozen rides stays in the low tens of MB).

## Implementation Notes

<!-- Filled in during/after implementation, not during drafting. What was
     actually built, especially where it deviates from Technical
     Decisions and why, plus any concrete results worth recording. -->
