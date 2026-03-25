"""最小运行时执行器。"""

from __future__ import annotations

from app.contracts.run import RunRequest, RunResult
from app.runtime.context import RunContext
from app.runtime.state import AgentState


class RuntimeExecutor:
    """为当前 Agent 状态执行一次 LLM 步骤。"""

    def execute(self, context: RunContext, state: AgentState) -> RunResult:
        """针对当前状态调用已配置的 LLM Provider。"""
        request = RunRequest(
            messages=state.messages,
            model=context.model,
            temperature=context.temperature,
            tools=context.tool_registry.get_tool_definitions(),
        )
        result = context.provider.chat(request)
        return result.model_copy(
            update={
                "run_id": context.run_id,
                "step_count": state.step_count,
            }
        )
