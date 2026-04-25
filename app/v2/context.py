"""V2 Context Builder。"""

from __future__ import annotations

from app.contracts.agent import AgentSpec, AgentTask, SharedWorkspace
from app.v2.memory import V2MemoryManager, V2MemoryPolicy


class ContextBuilder:
    """按 Agent 角色裁剪上下文。"""

    def __init__(self, memory_manager: V2MemoryManager | None = None) -> None:
        self.memory_manager = memory_manager or V2MemoryManager()

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
            "execution_notes": workspace.execution_notes[-self.memory_manager.policy.max_execution_notes :],
            "task_input": self.memory_manager.trim_for_prompt(dict(task.input_data)),
        }
        base_context.update(
            self.memory_manager.build_agent_context(agent_id=agent.agent_id, workspace=workspace)
        )
        return base_context


__all__ = ["ContextBuilder", "V2MemoryManager", "V2MemoryPolicy"]
