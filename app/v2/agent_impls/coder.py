"""Coder agent implementation."""

from __future__ import annotations

import json
from typing import Any

from app.contracts.agent import AgentArtifact, AgentResult, AgentSpec, AgentTask, SharedWorkspace
from app.contracts.run import RunMetrics
from app.v1.runtime.loop import AgentLoop
from app.v2.agent_impls.workspace_diff import build_workspace_patch, snapshot_workspace
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
        # 内层 V1 每步 = 一次「模型思考 + 可能工具」；修 bug/登录等通常需要多轮读文件、改代码、再跑测试。
        # 原先 max(max_retries+2, 3) 在测试失败回流时极易 3 步就触顶，表现为「死循环」类提示。
        _inner_cap = 32
        _inner_steps = min(_inner_cap, max(20, (task.max_retries or 0) + 12))
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
            max_steps=_inner_steps,
            run_timeout_seconds=120,
            tool_registry=context.tool_registry,
            persist_session_memory=False,
            root_run_id=context.run_id,
            parent_run_id=context.run_id,
            is_top_level=False,
        )
        after_snapshot = snapshot_workspace(context.workspace_root)
        patch = build_workspace_patch(
            workspace_root=context.workspace_root,
            before=before_snapshot,
            after=after_snapshot,
        )
        modified_files = patch["modified_files"]
        created_files = patch["created_files"]
        deleted_files = patch["deleted_files"]
        diff_previews = patch["diff_previews"]
        patch_diffs = patch["patch_diffs"]
        patch_stats = patch["patch_stats"]
        summary = result.final_output.strip() or "Coder 未返回可解析摘要。"
        loop_boundary = self._build_loop_boundary_note(inner_run_id=result.run_id, outer_run_id=context.run_id)
        risk_notes = self._build_risk_notes(
            result=result,
            modified_files=modified_files,
            created_files=created_files,
            deleted_files=deleted_files,
        )
        patch_artifact = self._build_patch_artifact(
            result=result,
            summary=summary,
            modified_files=modified_files,
            created_files=created_files,
            deleted_files=deleted_files,
            diff_previews=diff_previews,
            patch_diffs=patch_diffs,
            patch_stats=patch_stats,
            patch=patch,
            risk_notes=risk_notes,
            loop_boundary=loop_boundary,
            context=context,
        )
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.spec.agent_id,
            status="completed" if result.status == "completed" else "failed",
            summary=summary,
            usage=result.usage,
            metrics=result.metrics or RunMetrics(),
            output_data={
                "summary": summary,
                "run_id": result.run_id,
                "step_count": result.step_count,
                "status": result.status,
                "final_output": result.final_output,
                "modified_files": modified_files,
                "created_files": created_files,
                "deleted_files": deleted_files,
                "diff_previews": diff_previews,
                "patch_diffs": patch_diffs,
                "patch_stats": patch_stats,
                "patch_id": patch["patch_id"],
                "base_snapshot_id": patch["base_snapshot_id"],
                "head_snapshot_id": patch["head_snapshot_id"],
                "risk_notes": risk_notes,
                "loop_boundary": loop_boundary,
                "patch_artifact": patch_artifact,
            },
            artifacts=[
                AgentArtifact(
                    key="patch_summary",
                    type="patch",
                    summary=summary[:200],
                    producer_agent=self.spec.agent_id,
                    content=patch_artifact,
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
            docs_context = self._extract_docs_context(analysis_context)
            if docs_context:
                parts.append(f"知识库检索结果：{json.dumps(self._compact_docs_context(docs_context), ensure_ascii=False)}")
                parts.append(
                    "如果当前任务要求“写算法/给出实现方案/生成代码片段”，且没有明确目标文件，"
                    "请直接在最终答复中输出完整算法说明、C++ 示例代码和使用注意事项；"
                    "不要反问缺少具体编程任务，也不要把任务误判为项目结构分析。"
                )
        latest_test_result = prompt_context.get("latest_test_result")
        if latest_test_result:
            parts.append(f"最新测试反馈：{json.dumps(latest_test_result, ensure_ascii=False)}")
        if workspace.latest_patch_summary:
            parts.append(f"最近代码改动摘要：{workspace.latest_patch_summary}")
        if task.constraints:
            parts.append(f"约束：{'; '.join(task.constraints)}")
        parts.append(
            "边界说明：你运行在 CoderAgent 内层 v1 AgentLoop 中，只能完成当前编码任务；"
            "不要尝试调度 Planner/Analyst/Tester/Reviewer，外层 OrchestratorRuntime 负责多 Agent 编排。"
        )
        parts.append("如果用户目标是生成方案或代码片段而非修改仓库文件，可以直接给出完整内容，并说明未写入文件。")
        parts.append("完成后请明确说明修改了哪些文件、做了什么改动、还有什么风险。")
        return "\n".join(parts)

    def _extract_docs_context(self, analysis_context: object) -> dict[str, Any]:
        if not isinstance(analysis_context, dict):
            return {}
        docs_context = analysis_context.get("docs_context")
        return dict(docs_context) if isinstance(docs_context, dict) else {}

    def _compact_docs_context(self, docs_context: dict[str, Any]) -> dict[str, Any]:
        matches = docs_context.get("matches", [])
        compact_matches: list[dict[str, Any]] = []
        if isinstance(matches, list):
            for item in matches[:5]:
                if not isinstance(item, dict):
                    compact_matches.append({"content": str(item)[:600]})
                    continue
                compact_matches.append(
                    {
                        "title": item.get("title") or item.get("source") or item.get("path") or item.get("id"),
                        "content": str(item.get("content") or item.get("text") or item.get("snippet") or "")[:800],
                        "score": item.get("score"),
                    }
                )
        return {
            "query": docs_context.get("query"),
            "match_count": docs_context.get("match_count", len(compact_matches)),
            "matches": compact_matches,
            "error": docs_context.get("error"),
        }

    def _build_patch_artifact(
        self,
        *,
        result: Any,
        summary: str,
        modified_files: list[str],
        created_files: list[str],
        deleted_files: list[str],
        diff_previews: dict[str, str],
        patch_diffs: dict[str, str],
        patch_stats: dict[str, int],
        patch: dict[str, Any],
        risk_notes: list[str],
        loop_boundary: dict[str, object],
        context: AgentContext,
    ) -> dict[str, Any]:
        return {
            "schema_version": "v2.patch_artifact.v1",
            "patch_id": patch["patch_id"],
            "base_snapshot_id": patch["base_snapshot_id"],
            "head_snapshot_id": patch["head_snapshot_id"],
            "outer_run_id": context.run_id,
            "inner_run_id": result.run_id,
            "producer_agent": self.spec.agent_id,
            "summary": summary,
            "stats": patch_stats,
            "files": {
                "modified": modified_files,
                "created": created_files,
                "deleted": deleted_files,
            },
            "diff_previews": diff_previews,
            "patch_diffs": patch_diffs,
            "risk_notes": risk_notes,
            "loop_boundary": loop_boundary,
        }

    def _build_loop_boundary_note(self, *, inner_run_id: str | None, outer_run_id: str) -> dict[str, object]:
        return {
            "outer_orchestrator_run_id": outer_run_id,
            "inner_coder_run_id": inner_run_id,
            "inner_loop_role": "single_task_execution_unit",
            "is_second_orchestrator": False,
            "delegation_allowed": False,
            "explanation": (
                "CoderAgent 复用 v1 AgentLoop 作为局部编码执行单元；"
                "它不拥有多 Agent 调度权，所有 Planner/Analyst/Tester/Reviewer 委派仍由外层 OrchestratorRuntime 控制。"
            ),
        }

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
