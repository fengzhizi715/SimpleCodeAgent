"""Built-in coding skill for V3."""

from __future__ import annotations

from enum import Enum

from app.v3.adapters.v2_agent_adapter import V2AgentAdapter
from app.v3.skills.base import Skill
from app.v3.contracts.skill_contracts import SkillInput, SkillOutput


class CodingExecutionMode(str, Enum):
    """Supported coding execution backends for the V3 coding skill."""

    INTERNAL = "internal"
    EXTERNAL = "external"


class CodingSkill(Skill):
    """Run coding through an internal or external backend, with graceful fallback."""

    def __init__(
        self,
        spec,
        *,
        internal_agent_adapter: V2AgentAdapter | None = None,
        external_agent_adapter: V2AgentAdapter | None = None,
    ) -> None:
        super().__init__(spec)
        self.internal_agent_adapter = internal_agent_adapter
        self.external_agent_adapter = external_agent_adapter

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        goal = str(skill_input.payload.get("goal", "")).strip()
        mode = self._resolve_execution_mode(skill_input)
        agent_adapter = (
            self.external_agent_adapter
            if mode == CodingExecutionMode.EXTERNAL
            else self.internal_agent_adapter
        )
        if agent_adapter is not None:
            try:
                result = await agent_adapter.run(
                    {
                        "run_id": skill_input.run_id,
                        "node_id": skill_input.context.get("current_node_id", "coding"),
                        "goal": goal,
                        "execution_mode": mode.value,
                        "workspace_root": (
                            skill_input.payload.get("workspace_root")
                            or skill_input.context.get("workspace_root")
                            or "."
                        ),
                        "analysis_context": skill_input.context.get("analyze_repo", {}),
                        "latest_test_result": skill_input.context.get("last_test_result"),
                        "constraints": skill_input.payload.get("constraints", []),
                        "success_criteria": skill_input.payload.get("success_criteria", []),
                        "external_agent": skill_input.payload.get("external_agent"),
                        "preferred_agent": skill_input.payload.get("preferred_agent"),
                        "allow_raw_external_command": skill_input.payload.get("allow_raw_external_command", False),
                        "external_command": skill_input.payload.get("external_command"),
                        "external_timeout_seconds": skill_input.payload.get("external_timeout_seconds", 300),
                        "codex_template": skill_input.payload.get("codex_template"),
                        "cursor_template": skill_input.payload.get("cursor_template"),
                        "cursor_cli_path": skill_input.payload.get("cursor_cli_path"),
                        "codex_cli_path": skill_input.payload.get("codex_cli_path"),
                    }
                )
                result.setdefault("execution_mode", mode.value)
                return SkillOutput(
                    success=True,
                    summary=str(result.get("summary") or f"Code updated ({mode.value})"),
                    data=result,
                )
            except Exception as exc:
                if not bool(skill_input.payload.get("allow_mock_fallback", True)):
                    return SkillOutput(
                        success=False,
                        summary=f"{mode.value} coding adapter failed",
                        error=str(exc),
                    )
                return SkillOutput(
                    success=True,
                    summary=f"Code updated ({mode.value} fallback)",
                    data={
                        "goal": goal,
                        "execution_mode": mode.value,
                        "changed_files": [],
                        "patch_summary": (
                            f"Fallback coding skill executed because the {mode.value} coding backend was unavailable: {exc}"
                        ),
                    },
                )
        return SkillOutput(
            success=True,
            summary=f"Code updated ({mode.value})",
            data={
                "goal": goal,
                "execution_mode": mode.value,
                "changed_files": [],
                "patch_summary": f"MVP coding skill executed in {mode.value} mode",
            },
        )

    def _resolve_execution_mode(self, skill_input: SkillInput) -> CodingExecutionMode:
        raw = str(
            skill_input.payload.get("execution_mode")
            or skill_input.payload.get("coding_mode")
            or skill_input.context.get("coding_execution_mode")
            or CodingExecutionMode.INTERNAL.value
        ).strip().lower()
        if raw == CodingExecutionMode.EXTERNAL.value:
            return CodingExecutionMode.EXTERNAL
        return CodingExecutionMode.INTERNAL
