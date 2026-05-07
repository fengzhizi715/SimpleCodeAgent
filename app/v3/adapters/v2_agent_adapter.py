"""V2 agent adapter for V3."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class V2AgentAdapter:
    """Adapter around an async V2-style agent runner."""

    def __init__(self, v2_agent_runner: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]) -> None:
        self.v2_agent_runner = v2_agent_runner

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run the adapted agent."""
        return await self.v2_agent_runner(payload)
