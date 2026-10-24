"""Tests for scripts/inspect_activity.py"""

from anthropic.types import ToolParam

from scripts.inspect_activity import _read_only_tool_names
from src.ai.tools import TOOLS


def _tool(name: str, required: list[str]) -> ToolParam:
    return {
        "name": name,
        "description": "",
        "input_schema": {"type": "object", "properties": {}, "required": required},
    }


class TestReadOnlyToolNames:
    def test_selects_activity_id_tools_in_input_order(self) -> None:
        tools = [
            _tool("per_activity_b", ["activity_id"]),
            _tool("list_like", ["weeks"]),
            _tool("per_activity_a", ["activity_id"]),
        ]
        assert _read_only_tool_names(tools) == ["per_activity_b", "per_activity_a"]

    def test_current_tools(self) -> None:
        assert _read_only_tool_names(TOOLS) == [
            "get_activity_details",
            "get_activity_power_curve",
            "get_activity_training_load",
            "get_activity_efficiency",
            "get_activity_intervals",
            "get_activity_zones",
        ]
