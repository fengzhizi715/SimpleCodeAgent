"""V2 agent adapter for V3."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from app.contracts.agent import AgentTask, SharedWorkspace, TestReport
from app.core.config import get_effective_llm_base_url, get_effective_llm_model, settings
from app.llm.client import OpenAICompatibleProvider
from app.trace.recorder import JsonlTraceRecorder
from app.trace.repository import SQLiteTraceRepository
from app.db.sqlite import SQLiteDB
from app.v1.tools.registry import ToolRegistry
from app.v2.agents import CoderAgent
from app.v2.agent_impls.external_coder import ExternalCodingAgent
from app.v2.base import AgentContext


class V2AgentAdapter:
    """Adapter around an async V2-style agent runner."""

    def __init__(self, v2_agent_runner: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]) -> None:
        self.v2_agent_runner = v2_agent_runner

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run the adapted agent."""
        return await self.v2_agent_runner(payload)

    @classmethod
    def for_coder(cls, workspace_root: str | Path | None = None) -> "V2AgentAdapter":
        """Build an adapter around the V2 coder agent."""

        async def _run(payload: dict[str, Any]) -> dict[str, Any]:
            run_id = str(payload.get("run_id") or "").strip()
            if not run_id:
                raise ValueError("Missing run_id for V2 coder adapter.")

            resolved_model = get_effective_llm_model()
            if not resolved_model:
                raise ValueError("Missing model for V2 coder adapter. Configure LLM_MODEL first.")
            if not (settings.llm_api_key or settings.llm_service_token):
                raise ValueError(
                    "Missing auth credentials for V2 coder adapter. Configure LLM_API_KEY or LLM_SERVICE_TOKEN first."
                )

            resolved_workspace_root = Path(
                payload.get("workspace_root") or workspace_root or settings.workdir or "."
            ).expanduser().resolve()
            provider = OpenAICompatibleProvider(
                base_url=get_effective_llm_base_url(),
                api_key=settings.llm_api_key,
                service_token=settings.llm_service_token,
                auth_mode=settings.llm_auth_mode,
                reasoning_param_style=settings.llm_reasoning_param_style,
                model=resolved_model,
                timeout=settings.llm_timeout,
            )
            tool_registry = ToolRegistry(workspace_root=resolved_workspace_root)
            tool_registry.register_default_tools()
            trace_repository = SQLiteTraceRepository(SQLiteDB())
            context = AgentContext(
                provider=provider,
                model=resolved_model,
                reasoning_mode="default",
                tool_registry=tool_registry,
                trace_repository=trace_repository,
                trace_recorder=JsonlTraceRecorder(run_id=run_id),
                workspace_root=resolved_workspace_root,
                session_id=f"{run_id}:v3",
                run_id=run_id,
            )
            workspace = SharedWorkspace(
                session_id=context.session_id,
                run_id=run_id,
                user_goal=str(payload.get("goal") or ""),
                project_summary=_build_project_summary(payload),
                latest_test_result=_build_latest_test_result(payload),
            )
            task = AgentTask(
                session_id=context.session_id,
                run_id=run_id,
                step_id=str(payload.get("node_id") or "coding"),
                goal=str(payload.get("goal") or ""),
                step_type="coding",
                target_agent="coder",
                constraints=[str(item) for item in payload.get("constraints", []) if str(item).strip()],
                success_criteria=[
                    str(item)
                    for item in payload.get("success_criteria", ["Produce focused code changes and summarize them."])
                    if str(item).strip()
                ],
                max_retries=int(payload.get("max_retries", 1)),
            )
            prompt_context = {
                "project_summary": workspace.project_summary,
                "analysis_context": payload.get("analysis_context", {}),
            }
            if workspace.latest_test_result is not None:
                prompt_context["latest_test_result"] = workspace.latest_test_result.model_dump(mode="json")
            coder = CoderAgent()
            result = coder.run(
                task=task,
                workspace=workspace,
                context=context,
                prompt_context=prompt_context,
            )
            output = dict(result.output_data)
            output.setdefault("summary", result.summary)
            output.setdefault("status", result.status)
            return output

        return cls(_run)

    @classmethod
    def for_external_coder(cls, workspace_root: str | Path | None = None) -> "V2AgentAdapter":
        """Build an adapter around the V2 external coding agent."""

        async def _run(payload: dict[str, Any]) -> dict[str, Any]:
            run_id = str(payload.get("run_id") or "").strip()
            if not run_id:
                raise ValueError("Missing run_id for V2 external coder adapter.")

            resolved_workspace_root = Path(
                payload.get("workspace_root") or workspace_root or settings.workdir or "."
            ).expanduser().resolve()
            tool_registry = ToolRegistry(workspace_root=resolved_workspace_root)
            tool_registry.register_default_tools()
            trace_repository = SQLiteTraceRepository(SQLiteDB())
            context = AgentContext(
                provider=None,  # type: ignore[arg-type]
                model="external-coder",
                reasoning_mode="default",
                tool_registry=tool_registry,
                trace_repository=trace_repository,
                trace_recorder=JsonlTraceRecorder(run_id=run_id),
                workspace_root=resolved_workspace_root,
                session_id=f"{run_id}:v3",
                run_id=run_id,
            )
            workspace = SharedWorkspace(
                session_id=context.session_id,
                run_id=run_id,
                user_goal=str(payload.get("goal") or ""),
                project_summary=_build_project_summary(payload),
                latest_test_result=_build_latest_test_result(payload),
            )
            external_policy = {
                "enabled": True,
                "preferred_agent": str(payload.get("external_agent") or payload.get("preferred_agent") or "codex_cli"),
                "allow_raw_external_command": bool(payload.get("allow_raw_external_command", False)),
                "codex_template": str(payload.get("codex_template") or "").strip(),
                "cursor_template": str(payload.get("cursor_template") or "").strip(),
                "cursor_cli_path": str(payload.get("cursor_cli_path") or "").strip(),
                "codex_cli_path": str(payload.get("codex_cli_path") or "").strip(),
            }
            task = AgentTask(
                session_id=context.session_id,
                run_id=run_id,
                step_id=str(payload.get("node_id") or "coding"),
                goal=str(payload.get("goal") or ""),
                step_type="external_coding",
                target_agent="external_coder",
                success_criteria=[
                    str(item)
                    for item in payload.get("success_criteria", ["Produce focused code changes and summarize them."])
                    if str(item).strip()
                ],
                constraints=[str(item) for item in payload.get("constraints", []) if str(item).strip()],
                max_retries=int(payload.get("max_retries", 1)),
                input_data={
                    "external_agent": str(
                        payload.get("external_agent") or payload.get("preferred_agent") or "codex_cli"
                    ),
                    "external_prompt": str(payload.get("goal") or ""),
                    "external_command": str(payload.get("external_command") or "").strip(),
                    "external_timeout_seconds": int(payload.get("external_timeout_seconds", 300)),
                },
            )
            prompt_context = {
                "project_summary": workspace.project_summary,
                "analysis_context": payload.get("analysis_context", {}),
                "orchestrator_context": {
                    "policy": {
                        "external_coding": external_policy,
                    }
                },
            }
            if workspace.latest_test_result is not None:
                prompt_context["latest_test_result"] = workspace.latest_test_result.model_dump(mode="json")
            agent = ExternalCodingAgent()
            result = agent.run(
                task=task,
                workspace=workspace,
                context=context,
                prompt_context=prompt_context,
            )
            output = dict(result.output_data)
            output.setdefault("summary", result.summary)
            output.setdefault("status", result.status)
            return output

        return cls(_run)


def _build_project_summary(payload: dict[str, Any]) -> str:
    analysis_context = payload.get("analysis_context", {})
    if isinstance(analysis_context, dict):
        repo_profile = str(analysis_context.get("repo_profile") or "").strip()
        root_entries = analysis_context.get("root_entries", [])
        if repo_profile:
            summary = f"Repository profile: {repo_profile}."
            if isinstance(root_entries, list) and root_entries:
                summary += f" Root entries: {', '.join(str(item) for item in root_entries[:12])}."
            return summary
    return str(payload.get("project_summary") or "").strip()


def _build_latest_test_result(payload: dict[str, Any]) -> TestReport | None:
    raw = payload.get("latest_test_result")
    if not isinstance(raw, dict):
        return None
    executed_command = str(raw.get("executed_command") or "pytest -q").strip() or "pytest -q"
    summary = str(raw.get("summary") or raw.get("error") or "测试失败，需要修复。").strip()
    failure_type = raw.get("failure_type")
    return TestReport(
        status="failed",
        executed_command=executed_command,
        summary=summary,
        failure_type=str(failure_type) if failure_type is not None else None,
        key_logs=[str(raw.get("error") or "").strip()] if str(raw.get("error") or "").strip() else [],
    )
