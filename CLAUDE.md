# Project My AI Cycling Coach

Standalone Desktop application to generate training plans and monitor progress using Anthropic API (Sonnet 5.5).

## Readme

The README.md file contains all information regarding setup.

## Commands

- `pytest` — run all tests
- `ruff check .` — lint
- `ruff format .` — format code
- `mypy ./` — type checking

## Project Structure

- `src/` - Application source code
    - `ai/` - Code for AI agentic workflows
    - `analysis/` - Computation of metrics/statistics, signal processing tooling
    - `data/` - Data layer and connection to intervals.icu
    - `ui/` - Qt UI code
- `interval_detection` - Standalone Python package for interval detection with its own test bench (imported by the main application)
- `assets`- Assets used by App
- `tests`- Test bench for App
- `scripts/` - Tracked dev tooling that exercises production code paths for manual verification, run as `python -m scripts.<name>`
- `scratch/` - Gitignored, throwaway/ephemeral files (notes, one-off exploration scripts), never reviewed or kept

## Coding Conventions

- Type hints on all function signatures - parameters and return types
- f-strings for string formatting instead of format
- Logging: Root logger is set up in `src/logging_setup.py`, use logger = logging.getLogger(__name__) if logging required.
- Do not use `print()` statements, use the logger; Exception: Standalone scripts which benefit from direct feedback through command line
- Do not use `*` imports
- Comments: 
    - Only use comments where they explain a non-obvious Why
    - Do not use Function docstrings, the code with type hints should self-document

## Stories

- Work is planned as stories in `tasks/*.md` (template: `tasks/TEMPLATE.md`); the drafting and implementation process is defined tool-agnostically in `tasks/WORKFLOW.md`
- In Claude Code, use `/draft-story` and `/implement-story` to run that process

## Git

- Commits are done manually
- Releases are on the `main` branch, development should be in release branches
- Release branches are named `release/vN` (e.g. `release/v4`), the version number is fixed when the branch is opened
- Best practice for features is to branch off of the release branch
- All merges to `main` get a version tag (`v1`, `v2`, `v3`, ...) matching the release branch name. Note that this convention starts with the `v1` tag.

## Anthropic API calls

Since calls to the Anthropic API will be billed directly, always ask before making any such calls. If possible give a cost estimate.