"""最小运行时执行器。"""

from __future__ import annotations

from app.contracts.message import Message
from app.contracts.run import RunChoice, RunRequest, RunResult
from app.llm.client import LLMProviderError
from app.v1.runtime.context import RunContext
from app.v1.runtime.state import AgentState


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
        try:
            result = context.provider.chat(request)
        except LLMProviderError as exc:
            return self._fallback_result(
                context=context,
                state=state,
                message=f"模型调用失败，已触发降级处理：{exc}",
            )
        except Exception as exc:
            return self._fallback_result(
                context=context,
                state=state,
                message=f"模型执行出现未预期异常，已触发降级处理：{exc}",
            )

        if not result.choices:
            return self._fallback_result(
                context=context,
                state=state,
                message="模型返回了空结果，系统已提前结束本轮执行。",
            )

        first_choice = result.choices[0]
        if first_choice.message is None:
            return self._fallback_result(
                context=context,
                state=state,
                message="模型响应缺少 message 字段，系统已使用回退答案。",
            )

        return result.model_copy(
            update={
                "run_id": context.run_id,
                "step_count": state.step_count,
            }
        )

    def _fallback_result(
        self,
        *,
        context: RunContext,
        state: AgentState,
        message: str,
    ) -> RunResult:
        """在模型返回异常时构造可继续消费的回退结果。"""
        return RunResult(
            id=f"fallback-{context.run_id}-{state.step_count}",
            model=context.model,
            choices=[
                RunChoice(
                    index=0,
                    message=Message(role="assistant", content=message),
                    finish_reason="stop",
                )
            ],
            run_id=context.run_id,
            step_count=state.step_count,
            status="failed",
            final_output=message,
        )
