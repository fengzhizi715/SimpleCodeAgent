"""V1 tool adapter for V3."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class V1ToolAdapter:
    """Adapter around an async V1-style tool function."""

    def __init__(self, v1_tool_func: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]) -> None:
        self.v1_tool_func = v1_tool_func

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run the adapted tool."""
        return await self.v1_tool_func(payload)
