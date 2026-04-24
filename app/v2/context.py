"""V2 Context Builder。"""

from __future__ import annotations

from app.contracts.agent import AgentSpec, AgentTask, SharedWorkspace


class ContextBuilder:
    """按 Agent 角色裁剪上下文。"""

    def build(
        self,
        *,
        agent: AgentSpec,
        task: AgentTask,
        workspace: SharedWorkspace,
    ) -> dict[str, object]:
        """返回供指定 Agent 使用的上下文片段。"""
        base_context: dict[str, object] = {
            "user_goal": workspace.user_goal,
            "task_goal": task.goal,
            "step_type": task.step_type,
            "success_criteria": list(task.success_criteria),
            "constraints": list(task.constraints),
            "execution_notes": workspace.execution_notes[-5:],
        }
        if agent.agent_id == "planner":
            base_context["current_plan"] = (
                workspace.current_plan.model_dump() if workspace.current_plan else None
            )
            base_context["latest_test_result"] = (
                workspace.latest_test_result.model_dump() if workspace.latest_test_result else None
            )
            base_context["project_summary"] = workspace.project_summary
            return base_context
        if agent.agent_id == "analyst":
            base_context["project_summary"] = workspace.project_summary
            base_context["analysis_context"] = workspace.private_context.get("analyst", {})
            base_context["artifacts_index"] = [item.model_dump() for item in workspace.artifacts_index]
            base_context["current_plan"] = (
                workspace.current_plan.model_dump() if workspace.current_plan else None
            )
            return base_context
        if agent.agent_id == "coder":
            base_context["project_summary"] = workspace.project_summary
            base_context["latest_test_result"] = (
                workspace.latest_test_result.model_dump() if workspace.latest_test_result else None
            )
            base_context["latest_patch_summary"] = workspace.latest_patch_summary
            base_context["analysis_context"] = workspace.private_context.get("analyst", {})
            return base_context
        if agent.agent_id == "tester":
            base_context["latest_patch_summary"] = workspace.latest_patch_summary
            base_context["project_summary"] = workspace.project_summary
            base_context["coder_context"] = workspace.private_context.get("coder", {})
            base_context["analysis_context"] = workspace.private_context.get("analyst", {})
            return base_context
        if agent.agent_id == "reviewer":
            base_context["project_summary"] = workspace.project_summary
            base_context["latest_patch_summary"] = workspace.latest_patch_summary
            base_context["latest_test_result"] = (
                workspace.latest_test_result.model_dump() if workspace.latest_test_result else None
            )
            base_context["coder_context"] = workspace.private_context.get("coder", {})
            base_context["analysis_context"] = workspace.private_context.get("analyst", {})
            return base_context
        return base_context
