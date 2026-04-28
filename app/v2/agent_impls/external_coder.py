"""External coding agent executor for V2."""

from __future__ import annotations

from app.contracts.agent import AgentArtifact, AgentResult, AgentSpec, AgentTask, SharedWorkspace
from app.contracts.run import RunMetrics
from app.v2.agent_impls.llm_utils import parse_tool_content
from app.v2.agent_impls.workspace_diff import build_workspace_diff, snapshot_workspace
from app.v2.base import AgentBase, AgentContext
from app.v2.external_command_templates import build_external_command_from_template


class ExternalCodingAgent(AgentBase):
    """通过 shell_run 调用外部 Coding CLI（如 Codex/Cursor）执行复杂编码步骤。"""

    def __init__(self) -> None:
        super().__init__(
            AgentSpec(
                agent_id="external_coder",
                role="external_coder",
                description="Execute coding step via external coding CLI.",
                capabilities=["external-coding-cli", "patch-summary"],
            )
        )

    def run(
        self,
        *,
        task: AgentTask,
        workspace: SharedWorkspace,
        context: AgentContext,
        prompt_context: dict[str, object],
    ) -> AgentResult:
        external_agent = str(task.input_data.get("external_agent") or "").strip()
        external_prompt = str(task.input_data.get("external_prompt") or task.goal or "").strip()
        raw_command = str(task.input_data.get("external_command") or "").strip()
        orchestrator_context = prompt_context.get("orchestrator_context")
        policy = (
            orchestrator_context.get("policy", {})
            if isinstance(orchestrator_context, dict) and isinstance(orchestrator_context.get("policy"), dict)
            else {}
        )
        external_policy = policy.get("external_coding", {}) if isinstance(policy, dict) else {}
        if not isinstance(external_policy, dict):
            external_policy = {}
        if not bool(external_policy.get("enabled", False)):
            message = "external_coder 当前被运行策略禁用（external_coding.enabled=false）。"
            return AgentResult(
                task_id=task.task_id,
                agent_id=self.spec.agent_id,
                status="failed",
                summary=message,
                error_message=message,
            )
        preferred = str(external_policy.get("preferred_agent") or "").strip()
        effective_agent = external_agent or preferred or "codex_cli"
        allow_raw = bool(external_policy.get("allow_raw_external_command", False))
        template_overrides = {
            "codex_cli": str(external_policy.get("codex_template") or "").strip(),
            "cursor_cli": str(external_policy.get("cursor_template") or "").strip(),
        }
        template_overrides = {k: v for k, v in template_overrides.items() if v}
        command_source = "template"
        if raw_command and allow_raw:
            command = raw_command
            command_source = "raw"
        else:
            try:
                command = build_external_command_from_template(
                    external_agent=effective_agent,
                    prompt=external_prompt,
                    workspace_root=context.workspace_root,
                    template_overrides=template_overrides,
                    external_policy=external_policy,
                )
            except ValueError as exc:
                message = f"external_coder 无法构建外部命令：{exc}"
                return AgentResult(
                    task_id=task.task_id,
                    agent_id=self.spec.agent_id,
                    status="failed",
                    summary=message,
                    error_message=message,
                )

        before_snapshot = snapshot_workspace(context.workspace_root)
        shell_result = context.tool_registry.execute_tool(
            tool_name="shell_run",
            arguments={
                "command": command,
                "workdir": ".",
                "timeout": int(task.input_data.get("external_timeout_seconds") or 300),
                "max_output_chars": 40_000,
            },
            tool_call_id=f"{task.task_id}-external-coding",
        )
        payload = parse_tool_content(shell_result.content)
        ok = bool(payload.get("ok")) and not shell_result.is_error
        after_snapshot = snapshot_workspace(context.workspace_root)
        modified_files, created_files, deleted_files, diff_previews = build_workspace_diff(
            workspace_root=context.workspace_root,
            before=before_snapshot,
            after=after_snapshot,
        )

        stdout = str(payload.get("stdout") or "")
        stderr = str(payload.get("stderr") or "")
        tool_error = str(payload.get("error") or "")
        exit_code = payload.get("exit_code")
        failure_detail = stderr.strip() or stdout.strip() or tool_error.strip()
        if not failure_detail and exit_code is not None:
            failure_detail = f"exit_code={exit_code}"
        summary = (
            f"外部执行器 {effective_agent or 'external'} 完成编码步骤。"
            if ok
            else f"外部执行器 {effective_agent or 'external'} 执行失败。"
        )
        if not ok and failure_detail:
            summary = f"{summary} {failure_detail[:300]}"

        return AgentResult(
            task_id=task.task_id,
            agent_id=self.spec.agent_id,
            status="completed" if ok else "failed",
            summary=summary,
            metrics=RunMetrics(tool_call_count=1, tool_error_count=0 if ok else 1),
            output_data={
                "executor": "external",
                "external_agent": effective_agent,
                "selected_command": command,
                "selected_command_source": command_source,
                "ok": ok,
                "exit_code": payload.get("exit_code"),
                "stdout": stdout,
                "stderr": stderr,
                "error": tool_error,
                "modified_files": modified_files,
                "created_files": created_files,
                "deleted_files": deleted_files,
                "diff_previews": diff_previews,
            },
            artifacts=[
                AgentArtifact(
                    key="patch_summary",
                    type="patch",
                    summary=summary[:200],
                    producer_agent=self.spec.agent_id,
                    content={
                        "selected_command": command,
                        "modified_files": modified_files,
                        "created_files": created_files,
                        "deleted_files": deleted_files,
                        "error": tool_error,
                    },
                )
            ],
            error_message=None if ok else (failure_detail[:1000] or summary),
        )
