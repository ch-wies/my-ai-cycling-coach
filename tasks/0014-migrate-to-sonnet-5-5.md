---
title: Migrate AI model from Claude Sonnet 5 to Claude Sonnet 5.5
status: done   # see tasks/WORKFLOW.md for the lifecycle
release: v5     # see tasks/WORKFLOW.md; can be set before status: ready
---

## Problem / Context

The app's `AI_MODEL` constant (`src/constants.py:24`) is hardcoded to
`"claude-sonnet-5"`. Anthropic has since released Claude Sonnet 5.5
(`claude-sonnet-5-5`), a drop-in successor at the same per-token price
($2/$10 per MTok) with reported gains concentrated in agentic coding and
tool-use workloads — the exact shape of this app's AI features (plan
generation/adaptation, tool-using coach chat).

A review of the breaking changes between Sonnet 5 and Sonnet 5.5 found none
that apply to this codebase's usage:

- No `thinking` parameter is set anywhere (adaptive-thinking-off behavior
  change doesn't apply).
- No forced `tool_choice` (`"any"`/`"tool"`) is used — all tool-enabled
  calls (`src/ai/plan_adaptor.py:132`, `src/ui/workers.py:112`) omit
  `tool_choice`, defaulting to `auto`, which is unaffected.
- No computer-use tool, no advisor tool, no assistant-message prefill
  anywhere in `src/ai/` or `src/ui/workers.py`.
- Prompt caching (`cache_control: {"type": "ephemeral"}`, used in
  `src/ai/chat_session.py:124` and `src/ai/plan_adaptor.py:41,122,164,169`)
  is expected to carry over unchanged.

This makes the migration itself a one-line constant change; this story
exists to track doing that deliberately (confirming no regressions) rather
than as an incidental edit.

## Acceptance Criteria

- [ ] `src/constants.py:24` — `AI_MODEL` changed from `"claude-sonnet-5"`
      to `"claude-sonnet-5-5"`.
- [ ] All four call sites (`src/ai/plan_generator.py:51,80`,
      `src/ai/plan_adaptor.py:129,188`, `src/ui/workers.py:109`) continue to
      work unchanged — they consume `AI_MODEL`, no call-site edits expected.
- [ ] Plan generation (`plan_generator.generate_plan` /
      `generate_sessions`), plan adaptation (`plan_adaptor`), and the coach
      chat tool-use loop (`ui/workers.py`) are manually exercised end to end
      against the live Anthropic API on `claude-sonnet-5-5` and behave
      correctly (valid output, tool calls execute, no new errors).
- [ ] Prompt cache hits are confirmed to still register on
      `claude-sonnet-5-5` (`usage.cache_read_input_tokens` > 0 on a second
      request reusing the same cached prefix in chat or plan adaptation).
- [ ] `pytest`, `ruff check .`, `ruff format --check .`, and `mypy ./` all
      pass after the change.

## Technical Decisions

- Single-point change: only `AI_MODEL` in `src/constants.py` is edited. No
  call site, tool definition, or prompt text changes — the breaking-change
  review in Problem/Context found nothing else this codebase relies on that
  changed between Sonnet 5 and Sonnet 5.5.
- No model-ID configurability (env var, settings UI, etc.) is introduced —
  out of scope for this story; the constant stays hardcoded as it is today.
- Considered switching `plan_generator`/`plan_adaptor` to `claude-opus-5-5`
  instead of `claude-sonnet-5-5` (Opus's reported gains skew toward
  agentic/judgment-heavy work, which plan generation arguably is). Tested
  by generating the same plan from real saved goals with both models
  (`scratch/compare_plan_models.py`, outputs in `scratch/plan_compare/`;
  formerly under `dev_files/`) and manually reviewing the output. Verdict:
  little practical benefit from Opus for this task, at ~2x the cost
  (~$0.26 vs ~$0.53 per plan-narrative call, from actual token usage) —
  staying with `claude-sonnet-5-5` everywhere, per the single-constant
  change above.

## Test Plan

- Run `pytest`, `ruff check .`, `ruff format --check .`, `mypy ./` — all
  pass.
- Manual: generate a new training plan end-to-end via the UI and confirm
  output is well-formed (same as pre-migration behavior).
- Manual: run a plan adaptation that triggers at least one tool call (e.g.
  asks about recent activity) and confirm the tool-use loop completes
  correctly.
- Manual: have a coach chat conversation that spans at least two turns
  using tools, and inspect logged `usage.cache_read_input_tokens` on the
  second turn to confirm prompt caching still hits.

## Out of Scope

- Making `AI_MODEL` configurable (env var, UI setting, etc.).
- Adopting any Sonnet 5.5-specific new feature (e.g. `between_tools`
  thinking mode, per-message effort) — this story is a like-for-like model
  swap only.
- Re-tuning prompts or tool descriptions for the new model's behavior —
  only pursued later if manual testing surfaces a real regression.

## Implementation Notes

<!-- Filled in during/after implementation, not during drafting. What was
     actually built, especially where it deviates from Technical
     Decisions and why, plus any concrete results worth recording. -->

Implemented as drafted. The single code change is `AI_MODEL =
"claude-sonnet-5-5"` in `src/constants.py`.

- Small addition: the model mentions in README.md ("claude-sonnet-5") and
  the CLAUDE.md header ("Sonnet 5") were updated to Sonnet 5.5.
- Extended breaking-change review against Anthropic's Sonnet 5.5 migration
  guide, covering items the drafted review didn't list. None needed code:
  - History-editing check (thinking blocks are tied to unchanged earlier
    history; on newer accounts, edited history is a 400). Both tool loops
    (`ui/workers.py`, `ai/plan_adaptor.py`) append the full
    `response.content`, so they are append-only. Moving `cache_control`
    markers (plan_adaptor.py) is explicitly allowed. Chat history across
    turns stores text only, so no thinking blocks are replayed after
    edits.
  - Interim notes between tool calls may come back as empty `thinking`
    blocks instead of `text`. The chat may therefore show less text between
    tool calls; tool status messages are unaffected. This is behavioural,
    not breaking.
  - Effort levels are recalibrated (the default is still `high`; the app
    sets none). Not tuned, per "like-for-like".
  - Refusals: Sonnet 5.5 declines in more categories (`stop_reason:
    "refusal"`). A server-side fallback to Sonnet 5 was considered and left
    out to keep the swap like-for-like. A refusal surfaces through the
    existing "stopped unexpectedly" error or the chat warning.
  - The minimum cacheable prompt drops from 1,024 to 512 tokens. The first
    request after the switch writes the cache fresh.

Verification:
- `./check.sh`: all pass (361 tests).
- Manual end-to-end tests (run by the user in the UI): see below.
  - Generating a plan (22 weeks): Success
  - Adapting the plan with an addition to the goals and a tool call: Success
  - Chat with the coach confirming correct tool use and cache write/read: Success
  - Log check (`~/.my-ai-cycling-coach-test/app.log`, 2026-10-25): all 9
    requests used `claude-sonnet-5-5`, with no warnings or errors.
    - Plan adaptation: `tool_use` → `tool_use` → `end_turn`,
      `cache_read` 0 → 12,651 → 13,582.
    - Coach chat: `tool_use` → `tool_use` → `end_turn`, `cache_read`
      0 → 18,924 → 18,924.
    - Prompt caching hits from the second request on, in both flows.
