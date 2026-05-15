"""Skill execution helper."""

from __future__ import annotations

from app.v3.contracts.skill_contracts import SkillInput, SkillOutput
from app.v3.skills.registry import SkillRegistry


class SkillExecutor:
    """Resolve and execute skills from the registry."""

    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    async def execute(self, skill_name: str, skill_input: SkillInput) -> SkillOutput:
        """Execute a named skill."""
        skill = self.registry.get(skill_name)
        return await skill.execute(skill_input)

    @staticmethod
    def create_error_output(*, error: str, summary: str) -> SkillOutput:
        """Create a SkillOutput representing a failed execution."""
        return SkillOutput(
            success=False,
            summary=summary,
            error=error,
        )
