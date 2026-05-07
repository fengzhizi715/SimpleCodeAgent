"""V1 tool adapter for V3."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from app.v1.tools.base import Tool
from app.v1.tools.shell_run import ShellRunTool


class V1ToolAdapter:
    """Adapter around an async V1-style tool function."""

    def __init__(self, v1_tool_func: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]) -> None:
        self.v1_tool_func = v1_tool_func

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run the adapted tool."""
        return await self.v1_tool_func(payload)

    @classmethod
    def from_tool(
        cls,
        tool: Tool,
        *,
        tool_call_id: str = "v3-v1-tool-adapter",
    ) -> "V1ToolAdapter":
        """Wrap a concrete V1 tool instance as an async adapter."""

        async def _run(payload: dict[str, Any]) -> dict[str, Any]:
            result = tool.execute(payload, tool_call_id=tool_call_id)
            try:
                data = json.loads(result.content)
            except json.JSONDecodeError:
                data = {"content": result.content}
            if result.is_error:
                data.setdefault("ok", False)
                data.setdefault("error", result.content)
            return data

        return cls(_run)

    @classmethod
    def for_shell_run(cls, workspace_root: str | Path | None = None) -> "V1ToolAdapter":
        """Build an adapter for the V1 shell_run tool."""
        return cls.from_tool(ShellRunTool(workspace_root=workspace_root))
