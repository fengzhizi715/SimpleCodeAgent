"""Agent-backed skill implementation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.v3.contracts.skill_contracts import SkillInput, SkillOutput, SkillSpec
from app.v3.skills.base import Skill


class AgentSkill(Skill):
    """Wrap an async agent runner as a skill."""

    def __init__(self, spec: SkillSpec, agent_runner: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]) -> None:
        super().__init__(spec)
        self.agent_runner = agent_runner

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        try:
            result = await self.agent_runner(
                {
                    "run_id": skill_input.run_id,
                    "payload": skill_input.payload,
                    "context": skill_input.context,
                }
            )
        except Exception as exc:  # pragma: no cover - defensive branch
            return SkillOutput(
                success=False,
                summary="Agent skill failed",
                error=str(exc),
            )
        return SkillOutput(
            success=True,
            summary=str(result.get("summary", "Agent skill executed")),
            data=result,
        )
