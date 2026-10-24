"""Dump a live intervals.icu activity's streams and AI coach tool outputs.

Standalone dev tool for verifying data/tool changes against a real activity:
prints the raw stream summary (available_metrics plus per-metric count/min/
max/mean) and the output of every read-only AI coach tool, exercising the
same _execute_tool dispatch path used in production (not a reimplementation
of it). Requires a configured intervals.icu API key/athlete id (see
IntervalsClient) and live network access, so this stays a manual dev tool —
not wired into pytest.

Usage:
    python -m scripts.inspect_activity <activity_id>
"""

import sys

from anthropic.types import ToolUseBlock

from src.ai.tools import _execute_tool
from src.data.activity import Activity
from src.data.intervals_api import IntervalsClient

# Read-only tools only — mirrors the dispatch table in src/ai/tools.py
# (no write/mutating tools exist today; exclude any if added later).
_READ_ONLY_TOOLS = [
    "get_activity_details",
    "get_activity_power_curve",
    "get_activity_training_load",
    "get_activity_efficiency",
    "get_activity_intervals",
    "get_activity_zones",
]


def _print_stream_summary(activity: Activity) -> None:
    metrics = activity.available_metrics
    print(f"Available metrics: {metrics}")
    print()
    if metrics:
        print(activity.data[metrics].describe())


def _print_tool_outputs(activity_id: str, client: IntervalsClient) -> None:
    for tool_name in _READ_ONLY_TOOLS:
        block = ToolUseBlock(
            id=f"inspect_{tool_name}",
            name=tool_name,
            input={"activity_id": activity_id},
            type="tool_use",
        )
        print(f"--- {tool_name} ---")
        print(_execute_tool(block, client))
        print()


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 1
    activity_id = argv[0]

    client = IntervalsClient()
    activity = client.download_activity(activity_id)

    print(f"Activity {activity_id}")
    print("=" * 40)
    _print_stream_summary(activity)
    print()
    print("=" * 40)
    _print_tool_outputs(activity_id, client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
