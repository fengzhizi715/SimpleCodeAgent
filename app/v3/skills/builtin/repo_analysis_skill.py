"""Built-in repository analysis skill for V3."""

from __future__ import annotations

from app.v3.contracts.skill_contracts import SkillInput, SkillOutput
from app.v3.skills.base import Skill
from app.v3.skills.builtin.project_profile import inspect_workspace


class RepoAnalysisSkill(Skill):
    """Inspect the current workspace and expose a small repo profile."""

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        workspace_root = (
            skill_input.payload.get("workspace_root")
            or skill_input.context.get("workspace_root")
            or "."
        )
        profile = inspect_workspace(str(workspace_root))
        return SkillOutput(
            success=True,
            summary=f"Detected repo profile: {profile['repo_profile']}",
            data=profile,
        )
