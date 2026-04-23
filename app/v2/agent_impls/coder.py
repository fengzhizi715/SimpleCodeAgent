"""Coder agent implementation."""

from __future__ import annotations

import json
from typing import Any

from app.contracts.agent import AgentArtifact, AgentResult, AgentSpec, AgentTask, SharedWorkspace
from app.contracts.run import RunMetrics
from app.v1.runtime.loop import AgentLoop
from app.v2.agent_impls.workspace_diff import build_workspace_diff, snapshot_workspace
from app.v2.base import AgentBase, AgentContext


class CoderAgent(AgentBase):
    """复用 V1 AgentLoop 执行局部编码任务。

    这里复用的是 v1 的“单任务执行单元”，不是第二个 orchestrator。
    v2 的多 Agent 调度仍然只由外层 OrchestratorRuntime 负责。

    输入契约：
    - task.goal / success_criteria / constraints：当前编码步骤目标与约束。
    - prompt_context：project_summary / analysis_context / latest_test_result 等。
    - workspace：最近 patch/test 结果用于上下文拼装。

    输出契约：
    - AgentResult.status：completed 或 failed。
    - output_data：modified_files / created_files / deleted_files / diff_previews / risk_notes。
    - artifacts：patch_summary 工件。
    """

    def __init__(self, agent_loop: AgentLoop | None = None) -> None:
        super().__init__(
            AgentSpec(
                agent_id="coder",
                role="coder",
                description="Implement focused code changes with local validation.",
                capabilities=["code-edit", "tool-use", "patch-summary"],
            )
        )
        self.agent_loop = agent_loop or AgentLoop()

    def run(
        self,
        *,
        task: AgentTask,
        workspace: SharedWorkspace,
        context: AgentContext,
        prompt_context: dict[str, object],
    ) -> AgentResult:
        before_snapshot = snapshot_workspace(context.workspace_root)
        coder_task = self._build_task_prompt(task=task, prompt_context=prompt_context, workspace=workspace)
        result = self.agent_loop.run(
            provider=context.provider,
            model=context.model,
            task=coder_task,
            system_prompt=(
                "You are the Coder Agent in SimpleCodeAgent V2. "
                "Make local, minimal changes, respect existing boundaries, and summarize what changed."
            ),
            session_id=f"{context.session_id}:v2:coder",
            reasoning_mode=context.reasoning_mode,
            temperature=0.0,
            max_steps=max(task.max_retries + 2, 3),
            run_timeout_seconds=120,
            tool_registry=context.tool_registry,
            persist_session_memory=False,
            root_run_id=context.run_id,
            parent_run_id=context.run_id,
        )
        after_snapshot = snapshot_workspace(context.workspace_root)
        modified_files, created_files, deleted_files, diff_previews = build_workspace_diff(
            workspace_root=context.workspace_root,
            before=before_snapshot,
            after=after_snapshot,
        )
        summary = result.final_output.strip() or "Coder 未返回可解析摘要。"
        risk_notes = self._build_risk_notes(
            result=result,
            modified_files=modified_files,
            created_files=created_files,
            deleted_files=deleted_files,
        )
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.spec.agent_id,
            status="completed" if result.status == "completed" else "failed",
            summary=summary,
            usage=result.usage,
            metrics=result.metrics or RunMetrics(),
            output_data={
                "run_id": result.run_id,
                "step_count": result.step_count,
                "status": result.status,
                "final_output": result.final_output,
                "modified_files": modified_files,
                "created_files": created_files,
                "deleted_files": deleted_files,
                "diff_previews": diff_previews,
                "risk_notes": risk_notes,
            },
            artifacts=[
                AgentArtifact(
                    key="patch_summary",
                    type="patch",
                    summary=summary[:200],
                    producer_agent=self.spec.agent_id,
                    content={
                        "final_output": result.final_output,
                        "modified_files": modified_files,
                        "created_files": created_files,
                        "deleted_files": deleted_files,
                    },
                )
            ],
            error_message=None if result.status == "completed" else result.final_output,
        )

    def _build_task_prompt(
        self,
        *,
        task: AgentTask,
        prompt_context: dict[str, object],
        workspace: SharedWorkspace,
    ) -> str:
        parts = [
            f"任务目标：{task.goal}",
            f"成功标准：{'; '.join(task.success_criteria) or '完成当前步骤'}",
        ]
        project_summary = str(prompt_context.get("project_summary") or workspace.project_summary).strip()
        if project_summary:
            parts.append(f"项目分析：{project_summary}")
        analysis_context = prompt_context.get("analysis_context")
        if analysis_context:
            parts.append(f"分析详情：{json.dumps(analysis_context, ensure_ascii=False)}")
        latest_test_result = prompt_context.get("latest_test_result")
        if latest_test_result:
            parts.append(f"最新测试反馈：{json.dumps(latest_test_result, ensure_ascii=False)}")
        if workspace.latest_patch_summary:
            parts.append(f"最近代码改动摘要：{workspace.latest_patch_summary}")
        if task.constraints:
            parts.append(f"约束：{'; '.join(task.constraints)}")
        parts.append("完成后请明确说明修改了哪些文件、做了什么改动、还有什么风险。")
        return "\n".join(parts)

    def _build_risk_notes(
        self,
        *,
        result: Any,
        modified_files: list[str],
        created_files: list[str],
        deleted_files: list[str],
    ) -> list[str]:
        notes: list[str] = []
        if result.status != "completed":
            notes.append("Coder 运行未完成，当前改动可能不完整。")
        if not modified_files and not created_files and not deleted_files:
            notes.append("未检测到工作区文件变化，可能只产生了建议而未真正修改文件。")
        if deleted_files:
            notes.append("存在文件删除，请确认是否符合最小改动原则。")
        return notes
