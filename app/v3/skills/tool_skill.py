"""Tool-backed skill implementation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.v3.contracts.skill_contracts import SkillInput, SkillOutput, SkillSpec
from app.v3.skills.base import Skill


class ToolSkill(Skill):
    """Wrap an async tool-like function as a skill."""

    def __init__(self, spec: SkillSpec, tool_func: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]) -> None:
        super().__init__(spec)
        self.tool_func = tool_func

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        try:
            result = await self.tool_func(skill_input.payload)
        except Exception as exc:  # pragma: no cover - defensive branch
            return SkillOutput(
                success=False,
                summary="Tool skill failed",
                error=str(exc),
            )
        return SkillOutput(
            success=True,
            summary="Tool skill executed",
            data=result,
        )
