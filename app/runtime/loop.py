"""最小 Agent 循环。"""

from __future__ import annotations

from uuid import uuid4

from app.contracts.message import Message
from app.contracts.run import RunResult
from app.contracts.trace import TraceEvent
from app.core.exceptions import AppError
from app.llm.client import LLMProvider
from app.memory.repository import SQLiteMemoryRepository
from app.memory.session_memory import SessionMemory
from app.memory.summary_memory import SummaryMemory
from app.llm.parser import extract_final_text, extract_tool_calls
from app.runtime.context import RunContext
from app.runtime.executor import RuntimeExecutor
from app.runtime.state import AgentState
from app.tools.registry import ToolRegistry


class AgentLoop:
    """执行最小版“思考后结束”的 Agent 循环。"""

    def __init__(self, executor: RuntimeExecutor | None = None) -> None:
        self.executor = executor or RuntimeExecutor()

    def run(
        self,
        *,
        provider: LLMProvider,
        model: str,
        task: str,
        system_prompt: str,
        session_id: str,
        temperature: float = 0.0,
        max_steps: int = 3,
        tool_registry: ToolRegistry | None = None,
        session_memory: SessionMemory | None = None,
        summary_memory: SummaryMemory | None = None,
    ) -> RunResult:
        """执行最小 Agent 循环并返回标准化结果。"""
        run_id = str(uuid4())
        registry = tool_registry or ToolRegistry()
        session_store = session_memory or SessionMemory(SQLiteMemoryRepository())
        summary_store = summary_memory or SummaryMemory(session_store.repository)
        history_messages = session_store.load(session_id)
        context = RunContext(
            run_id=run_id,
            session_id=session_id,
            provider=provider,
            model=model,
            tool_registry=registry,
            session_memory=session_store,
            summary_memory=summary_store,
            system_prompt=system_prompt,
            temperature=temperature,
            max_steps=max_steps,
        )
        state = AgentState(
            run_id=run_id,
            session_id=session_id,
            task=task,
            messages=[
                Message(role="system", content=context.effective_system_prompt),
                *history_messages,
                Message(role="user", content=task),
            ],
            history_message_count=len(history_messages),
            trace_events=[
                TraceEvent(
                    run_id=run_id,
                    event_type="run_started",
                    message="Agent run started.",
                    payload={"task": task, "session_id": session_id},
                )
            ],
        )

        while state.step_count < context.max_steps:
            state.step_count += 1
            state.trace_events.append(
                TraceEvent(
                    run_id=run_id,
                    event_type="step_started",
                    message="Executor step started.",
                    payload={"step_count": state.step_count},
                )
            )
            result = self.executor.execute(context, state)

            if not result.choices:
                state.status = "failed"
                raise AppError("LLM returned no choices.")

            assistant_message = result.choices[0].message
            state.messages.append(assistant_message)
            state.trace_events.append(
                TraceEvent(
                    run_id=run_id,
                    event_type="llm_response",
                    message="LLM returned a response.",
                    payload={
                        "step_count": state.step_count,
                        "finish_reason": result.choices[0].finish_reason,
                    },
                )
            )

            tool_calls = extract_tool_calls(result)
            if tool_calls:
                self._handle_tool_calls(
                    tool_calls=tool_calls,
                    context=context,
                    state=state,
                )
                continue

            if self._is_final_answer(result):
                final_output = extract_final_text(result)
                state.status = "completed"
                state.final_output = final_output
                state.trace_events.append(
                    TraceEvent(
                        run_id=run_id,
                        event_type="run_completed",
                        message="Agent run completed with final answer.",
                        payload={"step_count": state.step_count},
                    )
                )
                final_result = result.model_copy(
                    update={
                        "run_id": run_id,
                        "session_id": session_id,
                        "step_count": state.step_count,
                        "status": state.status,
                        "final_output": final_output,
                        "trace": state.trace_events,
                    }
                )
                self._persist_session_messages(context, state)
                self._persist_run_metadata(context, state, final_result)
                return final_result

        state.status = "max_steps_exceeded"
        state.trace_events.append(
            TraceEvent(
                run_id=run_id,
                event_type="run_stopped",
                message="Agent run stopped after reaching the max step limit.",
                payload={"step_count": state.step_count},
            )
        )
        raise AppError("Agent loop reached max steps without a final answer.")

    def _persist_session_messages(self, context: RunContext, state: AgentState) -> None:
        """持久化当前运行新产生的消息。"""
        start_index = 1 + state.history_message_count
        new_messages = [
            message
            for message in state.messages[start_index:]
            if message.role in {"user", "assistant", "tool"}
        ]
        context.session_memory.append(context.session_id, new_messages)

    def _persist_run_metadata(
        self,
        context: RunContext,
        state: AgentState,
        result: RunResult,
    ) -> None:
        """当仓储支持时，持久化 run 与 trace 元数据。"""
        repository = context.session_memory.repository
        if hasattr(repository, "save_run"):
            repository.save_run(result, state.task)
        if hasattr(repository, "save_trace_events"):
            repository.save_trace_events(context.run_id, result.trace)

    def _is_final_answer(self, result: RunResult) -> bool:
        """判断 assistant 是否已经返回普通最终答案。"""
        if not result.choices:
            return False

        message = result.choices[0].message
        if extract_tool_calls(result):
            return False
        return bool(message.content and message.content.strip())

    def _handle_tool_calls(
        self,
        *,
        tool_calls: list,
        context: RunContext,
        state: AgentState,
    ) -> None:
        """执行工具调用，并将工具结果追加到状态消息中。"""
        for tool_call in tool_calls:
            state.trace_events.append(
                TraceEvent(
                    run_id=context.run_id,
                    event_type="tool_call_received",
                    message="Tool call received from LLM.",
                    payload={
                        "step_count": state.step_count,
                        "tool_name": tool_call.function.name,
                        "tool_call_id": tool_call.id,
                    },
                )
            )
            tool_result = context.tool_registry.execute_tool_call(tool_call)
            state.messages.append(tool_result.to_message())
            state.trace_events.append(
                TraceEvent(
                    run_id=context.run_id,
                    event_type="tool_result_appended",
                    message="Tool result appended for next LLM step.",
                    payload={
                        "step_count": state.step_count,
                        "tool_name": tool_result.name,
                        "tool_call_id": tool_result.tool_call_id,
                        "is_error": tool_result.is_error,
                    },
                )
            )
