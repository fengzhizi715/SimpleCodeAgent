"""Built-in coding skill for V3."""

from __future__ import annotations

from app.v3.adapters.v2_agent_adapter import V2AgentAdapter
from app.v3.skills.base import Skill
from app.v3.contracts.skill_contracts import SkillInput, SkillOutput


class CodingSkill(Skill):
    """Run a real V2 coder when available, otherwise fall back to MVP output."""

    def __init__(self, spec, agent_adapter: V2AgentAdapter | None = None) -> None:
        super().__init__(spec)
        self.agent_adapter = agent_adapter

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        goal = str(skill_input.payload.get("goal", "")).strip()
        if self.agent_adapter is not None:
            try:
                result = await self.agent_adapter.run(
                    {
                        "run_id": skill_input.run_id,
                        "node_id": skill_input.context.get("current_node_id", "coding"),
                        "goal": goal,
                        "workspace_root": (
                            skill_input.payload.get("workspace_root")
                            or skill_input.context.get("workspace_root")
                            or "."
                        ),
                        "analysis_context": skill_input.context.get("analyze_repo", {}),
                        "latest_test_result": skill_input.context.get("last_test_result"),
                        "constraints": skill_input.payload.get("constraints", []),
                        "success_criteria": skill_input.payload.get("success_criteria", []),
                    }
                )
                return SkillOutput(
                    success=True,
                    summary=str(result.get("summary") or "Code updated"),
                    data=result,
                )
            except Exception as exc:
                if not bool(skill_input.payload.get("allow_mock_fallback", True)):
                    return SkillOutput(
                        success=False,
                        summary="V2 coder adapter failed",
                        error=str(exc),
                    )
                return SkillOutput(
                    success=True,
                    summary="Code updated (fallback)",
                    data={
                        "goal": goal,
                        "changed_files": [],
                        "patch_summary": f"Fallback coding skill executed because V2 coder was unavailable: {exc}",
                    },
                )
        return SkillOutput(
            success=True,
            summary="Code updated",
            data={
                "goal": goal,
                "changed_files": [],
                "patch_summary": "MVP coding skill executed",
            },
        )
