---
title: Introduce scripts/ and scratch/ folders for dev tooling
status: ready   # see tasks/WORKFLOW.md for the lifecycle
release: v5     # see tasks/WORKFLOW.md; can be set before status: ready
---

## Problem / Context

This story was prompted by a discoverability problem: a dev/test script
("print all tool output for an activity") was being looked for and
couldn't be found. It turned out to exist — `src/data/inspect_activity.py`
— it wasn't lost, just not where it would be expected: mixed in with
application source code under `src/data/` rather than living somewhere
obviously dedicated to dev/test tooling.

`src/data/inspect_activity.py` and `src/data/export_for_bench.py` are both
standalone, non-production dev scripts (manual verification tools run from
the command line), not imported by any production code
(`export_for_bench.py` is only referenced via a hint string in
`interval_detection/bench/label_tool.py`). A dedicated top-level folder for
dev/test scripts worth keeping would make them easy to find, and keeps
one-off tooling separate from "real" application source.

Separately, the repo already has `dev_files/` — a gitignored scratch
folder for genuinely throwaway files. Its name is ambiguous (not obviously
"this is not reviewed, not kept, not even version controlled"); renaming it
to `scratch/` says that more clearly, and disambiguates it from the new
tracked `scripts/` folder.

This story introduces a clear split:

- `scripts/` — a new, tracked (version-controlled) top-level folder for dev
  scripts worth keeping. `inspect_activity.py` and `export_for_bench.py` move
  here.
- `scratch/` — `dev_files/`, renamed, still gitignored, for genuinely
  throwaway/ephemeral files (notes, one-off exploration scripts) that are
  never meant to be committed.

## Acceptance Criteria

- [ ] New top-level `scripts/` folder exists, tracked in git, with
      `scripts/__init__.py` making it an importable package.
- [ ] `src/data/inspect_activity.py` moved to `scripts/inspect_activity.py`;
      runnable as `python -m scripts.inspect_activity <activity_id>`
      (replacing `python -m src.data.inspect_activity <activity_id>`);
      behavior unchanged (stream summary + per-read-only-tool dump via
      `_execute_tool`).
- [ ] `src/data/export_for_bench.py` moved to `scripts/export_for_bench.py`;
      runnable as `python -m scripts.export_for_bench <activity_id> [...]`
      (replacing `python -m src.data.export_for_bench ...`); `_BENCH_DIR`'s
      path calculation updated for the new file depth so it still resolves
      to `interval_detection/bench`; behavior otherwise unchanged.
- [ ] `interval_detection/bench/label_tool.py`'s hint string updated from
      `python -m src.data.export_for_bench` to `python -m
      scripts.export_for_bench`.
- [ ] `src/data/intervals_api.py`'s module docstring reference to
      `src/data/inspect_activity.py` updated to `scripts/inspect_activity.py`.
- [ ] `dev_files/` renamed to `scratch/`; `.gitignore`'s `dev_files/` entry
      updated to `scratch/`; all existing contents preserved under the new
      name (this is only relevant for the machine where this change is executed). The stale `__pycache__/` under the old
      folder is not carried over (regenerates automatically, already covered
      by the top-level `__pycache__/` gitignore pattern).
- [ ] Change all comments and references to `dev_files` within the local scripts and files currently located in this folder.
- [ ] CLAUDE.md's Project Structure section documents both `scripts/`
      (tracked dev tooling that exercises production code paths for manual
      verification) and `scratch/` (gitignored, throwaway/ephemeral files,
      never reviewed or kept).
- [ ] `ruff check .`, `ruff format --check .`, `mypy ./`, and `pytest` all
      pass after the move — `scripts/` is held to the same conventions as
      `src/` (type hints, no scope carve-out in `pyproject.toml`).

## Technical Decisions

- `scripts/` is a real Python package (`scripts/__init__.py`), not a bag of
  loose files, so `python -m scripts.<name>` keeps working exactly like the
  current `python -m src.data.<name>` invocations — no `sys.path` insert
  hacks needed, unlike the throwaway scripts in `scratch/`.
- `export_for_bench.py`'s `_BENCH_DIR = Path(__file__).resolve().parents[2]
  / "interval_detection" / "bench"` currently climbs `data/ -> src/ ->
  <repo root>` (2 levels) from `src/data/export_for_bench.py`. From
  `scripts/export_for_bench.py`, the repo root is only 1 level up, so this
  becomes `parents[1]`.
- Any scripts carried over into `scratch/` keep their existing structure
  (e.g. a `sys.path.insert(0, ... parents[1])` shim, since `scratch/` is
  not a package) — only comments/references naming `dev_files/` are
  updated to `scratch/`.
- No coverage tooling is added in this story (there is none configured
  today — `pytest` runs without `--cov`, no `[tool.coverage]` section).
  Having `scripts/` as a separate top-level folder makes excluding it
  trivial whenever coverage *is* introduced later; that's a side benefit of
  this restructuring, not something this story sets up.
- `scripts/` is not exempted from `ruff`/`mypy` scope in `pyproject.toml` —
  both commands already run recursively from the repo root (`ruff check .`,
  `mypy ./`), and CLAUDE.md's coding conventions already anticipate
  standalone scripts (e.g. the `print()` exception), so no new carve-out is
  needed.

## Test Plan

- Run `./check.sh` (ruff check, ruff format --check, mypy, pytest) and
  confirm everything passes after the move.
- Manual: `python -m scripts.inspect_activity <a real activity id>` runs
  successfully against a live activity and produces the same output shape
  as before the move (stream summary, then one dump per read-only tool).
- Manual: `python -m scripts.export_for_bench <a real activity id>` runs
  successfully and writes `interval_detection/bench/activities/<id>.csv`
  plus seeds `interval_detection/bench/labels/<id>.json` as before —
  confirms the `_BENCH_DIR` path fix is correct.
- Manual: confirm `scratch/` contains everything `dev_files/` previously
  had, `dev_files/` no longer exists, and `git status` stays clean after
  adding a new file under `scratch/` (confirms it's still gitignored).

## Out of Scope

- Adding coverage tooling/config — deferred, as discussed above; this story
  only makes that easier to add later, it doesn't add it.
- Rewriting references to the old `src/data/inspect_activity.py` /
  `src/data/export_for_bench.py` paths inside existing `tasks/*.md` story
  files (0004, 0005, 0007) — those are a historical record of decisions
  made at the time and are left unchanged.
- Implementing story 0007 (deriving `_READ_ONLY_TOOLS` from `TOOLS`) — it
  remains a separate, unimplemented story; once it proceeds, it will target
  `scripts/inspect_activity.py` at its new location.
- Any behavioral change to `inspect_activity.py` or `export_for_bench.py`
  beyond the import/path fixes required by the move.

## Implementation Notes

<!-- Filled in during/after implementation, not during drafting. What was
     actually built, especially where it deviates from Technical
     Decisions and why, plus any concrete results worth recording. -->
