---
title: Derive inspect_activity.py's read-only tool list from TOOLS
status: ready   # see tasks/WORKFLOW.md for the lifecycle
release: v5     # see tasks/WORKFLOW.md; can be set before status: ready
---

## Problem / Context

`src/data/inspect_activity.py` (added in story 0005) hard-codes
`_READ_ONLY_TOOLS` as a literal list of 6 tool names:

```python
_READ_ONLY_TOOLS = [
    "get_activity_details",
    "get_activity_power_curve",
    "get_activity_training_load",
    "get_activity_efficiency",
    "get_activity_intervals",
    "get_activity_zones",
]
```

This list exists to iterate "every tool that takes an `activity_id` and is
safe to call read-only" when dumping AI-tool output for a real activity.
It was flagged during review of 0005: nothing keeps it in sync with
`TOOLS` in `src/ai/tools.py` — a new per-activity read tool added there in
the future silently won't show up in `inspect_activity.py`'s dump unless
someone remembers to update this separate list too.

Looking at the current `TOOLS` definitions, the distinction the hard-coded
list is actually drawing is structural: every entry in `TOOLS` requires
`activity_id` in its `input_schema` except `list_recent_activities` (which
takes `weeks` instead). That structural property can be checked
programmatically instead of hand-maintained.

Known limitation, deliberately not solved by this story: filtering on
"requires `activity_id`" cannot distinguish read-only from mutating tools.
No mutating tools exist in `TOOLS` today (confirmed by inspection), so the
filter and the intended "read-only" meaning coincide right now. If a
mutating tool requiring `activity_id` is ever added to `TOOLS`, this
filter would need revisiting — see Out of Scope.

## Acceptance Criteria

- [ ] `_READ_ONLY_TOOLS` in `src/data/inspect_activity.py` is no longer a
      hand-maintained literal list of names — it's derived from `TOOLS`
      (`src/ai/tools.py`).
- [ ] The derived list, run against today's `TOOLS`, produces the same six
      tool names in the same order as the current hard-coded list
      (`get_activity_details`, `get_activity_power_curve`,
      `get_activity_training_load`, `get_activity_efficiency`,
      `get_activity_intervals`, `get_activity_zones`) — no behavior change
      for `inspect_activity.py`'s existing output.
- [ ] `list_recent_activities` continues to be excluded, because it derives
      this from schema shape (no `activity_id` in `required`), not from a
      name check.
- [ ] Adding a new tool to `TOOLS` whose `input_schema["required"]`
      includes `"activity_id"` makes it appear in `inspect_activity.py`'s
      dump automatically — verified by a unit test, not just by reasoning
      about the code.
- [ ] The known read-only/mutating limitation is documented with a code
      comment at the derivation site (not just in this story), so a future
      author adding a mutating tool sees the warning where it matters.

## Technical Decisions

- New helper, local to `src/data/inspect_activity.py` (not exported from
  `src/ai/tools.py` — this is a dev-tool concern, not something the
  production tool-dispatch code needs, so it stays out of `tools.py`):
  ```python
  def _read_only_tool_names(tools: list[ToolParam]) -> list[str]:
  ```
  Filters `tools` for entries where `"activity_id" in
  tool["input_schema"]["required"]`, returning names in `tools`'
  declaration order (i.e. `TOOLS`' existing order, minus
  `list_recent_activities`). Replaces the `_READ_ONLY_TOOLS` literal;
  call site becomes `_read_only_tool_names(TOOLS)`.
- The limitation callout from Problem / Context is written as a short
  comment directly above `_read_only_tool_names`'s definition, e.g. noting
  that the filter assumes every `activity_id`-requiring tool is read-only,
  true today but not guaranteed if a mutating tool is ever added.

## Test Plan

- Unit test in a new `tests/test_inspect_activity.py`: build a small fake
  `list[ToolParam]` (2-3 entries: one requiring `activity_id`, one not,
  mirroring `list_recent_activities` vs the rest) and assert
  `_read_only_tool_names` returns exactly the expected subset, in input
  order.
- Unit test: run `_read_only_tool_names(TOOLS)` against the real, current
  `TOOLS` list and assert it equals the six known tool names in their
  current order — locks in the "no behavior change" acceptance criterion
  and will fail loudly (prompting a deliberate update) if `TOOLS`' shape
  changes in a way that affects this.
- Manual: none required — this only touches a dev-only script's internal
  list-building logic, not anything network-dependent or user-facing.

## Out of Scope

- Adding an explicit read-only/mutating marker or flag to tool
  definitions in `src/ai/tools.py` — would properly close the limitation
  noted in Problem / Context, but there's nothing to mark today (no
  mutating tools exist), so it's speculative work. Revisit when/if a
  mutating tool is actually added.
- Any change to `TOOLS`, tool dispatch, or tool behavior in
  `src/ai/tools.py` itself — this story only changes how
  `inspect_activity.py` builds its internal iteration list.

## Implementation Notes

<!-- Filled in during/after implementation, not during drafting. What was
     actually built, especially where it deviates from Technical
     Decisions and why, plus any concrete results worth recording. -->
