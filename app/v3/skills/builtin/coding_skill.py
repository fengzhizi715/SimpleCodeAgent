"""Built-in coding skill for V3."""

from __future__ import annotations

from app.v3.skills.base import Skill
from app.v3.contracts.skill_contracts import SkillInput, SkillOutput


class CodingSkill(Skill):
    """Return a minimal coding summary."""

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        goal = str(skill_input.payload.get("goal", "")).strip()
        return SkillOutput(
            success=True,
            summary="Code updated",
            data={
                "goal": goal,
                "changed_files": [],
                "patch_summary": "MVP coding skill executed",
            },
        )
