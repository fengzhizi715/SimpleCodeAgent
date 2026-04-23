"""最小 Agent 循环。"""

from __future__ import annotations

import json
from time import monotonic
from uuid import uuid4

from app.contracts.message import ChatMessage
from app.contracts.run import RunChoice, RunMetrics, RunResult
from app.core.logger import get_logger, log_context
from app.llm.client import LLMProvider
from app.llm.parser import extract_final_text, extract_tool_calls
from app.trace.events import make_trace_event
from app.v1.memory.repository import SQLiteMemoryRepository
from app.v1.memory.session_memory import SessionMemory
from app.v1.memory.summary_memory import SummaryMemory
from app.v1.planner.base import Planner
from app.v1.runtime.context import RunContext
from app.v1.runtime.direct_tool_executor import DirectToolExecutor
from app.v1.runtime.executor import RuntimeExecutor
from app.v1.runtime.plan_executor import PlanExecutor
from app.v1.runtime.state import AgentState
from app.v1.runtime.write_intent_parser import WriteIntentParser
from app.v1.tools.registry import ToolRegistry
from app.trace.recorder import JsonlTraceRecorder
from app.trace.repository import SQLiteTraceRepository

logger = get_logger(__name__)


class AgentLoop:
    """执行最小版“思考后结束”的 Agent 循环。"""

    def __init__(self, executor: RuntimeExecutor | None = None) -> None:
        self.executor = executor or RuntimeExecutor()
        self.write_intent_parser = WriteIntentParser()
        self.direct_tool_executor = DirectToolExecutor(
            write_intent_parser=self.write_intent_parser
        )
        self.plan_executor = PlanExecutor(
            run_callable=self.run,
            direct_tool_executor=self.direct_tool_executor,
        )

    def run(
        self,
        *,
        provider: LLMProvider,
        model: str,
        task: str,
        system_prompt: str,
        session_id: str,
        reasoning_mode: str = "default",
        temperature: float = 0.0,
        max_steps: int = 3,
        run_timeout_seconds: int = 120,
        tool_registry: ToolRegistry | None = None,
        session_memory: SessionMemory | None = None,
        summary_memory: SummaryMemory | None = None,
        persist_session_memory: bool = True,
        root_run_id: str | None = None,
        parent_run_id: str | None = None,
    ) -> RunResult:
        """执行最小 Agent 循环并返回标准化结果。"""
        run_id = str(uuid4())
        effective_root_run_id = root_run_id or run_id
        with log_context(run_id=run_id, session_id=session_id):
            started_at = monotonic()
            registry = tool_registry or ToolRegistry()
            session_store = session_memory or SessionMemory(SQLiteMemoryRepository())
            summary_store = summary_memory or SummaryMemory(session_store.repository)
            trace_repository = SQLiteTraceRepository(session_store.repository.db)
            trace_recorder = JsonlTraceRecorder(run_id=run_id)
            history_messages = session_store.load(session_id)
            context = RunContext(
                run_id=run_id,
                root_run_id=effective_root_run_id,
                parent_run_id=parent_run_id,
                session_id=session_id,
                provider=provider,
                model=model,
                reasoning_mode=reasoning_mode,
                tool_registry=registry,
                session_memory=session_store,
                summary_memory=summary_store,
                trace_recorder=trace_recorder,
                trace_repository=trace_repository,
                system_prompt=system_prompt,
                temperature=temperature,
                max_steps=max_steps,
                run_timeout_seconds=run_timeout_seconds,
                persist_session_memory=persist_session_memory,
            )
            state = AgentState(
                run_id=run_id,
                session_id=session_id,
                task=task,
                max_steps=max_steps,
                messages=[
                    ChatMessage(role="system", content=context.effective_system_prompt),
                    *history_messages,
                    ChatMessage(role="user", content=task),
                ],
                history_message_count=len(history_messages),
                trace_events=[],
            )
            self._append_trace_event(
                context=context,
                state=state,
                event_type="run_started",
                message="Agent run started.",
                payload={"task": task},
            )
            logger.info(
                "Starting agent loop: model=%s max_steps=%s timeout=%ss history_messages=%s",
                model,
                max_steps,
                run_timeout_seconds,
                len(history_messages),
            )

            while state.step_count < context.max_steps:
                if monotonic() - started_at >= context.run_timeout_seconds:
                    return self._build_timeout_result(
                        context=context,
                        state=state,
                        started_at=started_at,
                    )

                state.step_count += 1
                logger.info(
                    "Running agent step: step=%s/%s",
                    state.step_count,
                    context.max_steps,
                )
                self._append_trace_event(
                    context=context,
                    state=state,
                    event_type="step_started",
                    message="Executor step started.",
                    payload={"step_count": state.step_count},
                )
                self._append_trace_event(
                    context=context,
                    state=state,
                    event_type="llm_called",
                    message="LLM called.",
                    payload={"step_count": state.step_count, "model": context.model},
                )
                state.llm_call_count += 1
                result = self.executor.execute(context, state)
                if not result.choices:
                    return self._build_fallback_final_result(
                        context=context,
                        state=state,
                        started_at=started_at,
                        status="failed",
                        message="模型返回空结果，系统已结束本次运行。",
                        event_type="llm_empty_result",
                    )

                self._append_trace_event(
                    context=context,
                    state=state,
                    event_type="llm_responded",
                    message="LLM responded.",
                    payload={
                        "step_count": state.step_count,
                        "finish_reason": result.choices[0].finish_reason,
                    },
                )

                tool_calls = extract_tool_calls(result)
                if tool_calls:
                    if not context.tool_registry.get_tool_definitions():
                        return self._handle_hallucinated_tool_calls_without_registry(
                            context=context,
                            state=state,
                            started_at=started_at,
                            result=result,
                            reasoning_mode=reasoning_mode,
                        )
                    logger.info(
                        "LLM requested tool calls: step=%s tool_count=%s",
                        state.step_count,
                        len(tool_calls),
                    )
                    assistant_message = result.choices[0].message
                    state.messages.append(assistant_message)
                    self._handle_tool_calls(
                        tool_calls=tool_calls,
                        context=context,
                        state=state,
                    )
                    continue

                if result.status == "failed":
                    logger.error(
                        "Agent step returned fallback result: step=%s message=%s",
                        state.step_count,
                        result.final_output,
                    )
                    return self._build_fallback_final_result(
                        context=context,
                        state=state,
                        started_at=started_at,
                        status="failed",
                        message=result.final_output or "模型执行失败，系统已返回回退结果。",
                        event_type="llm_fallback_result",
                    )

                if self._is_final_answer(result):
                    assistant_message = result.choices[0].message
                    state.messages.append(assistant_message)
                    final_output = extract_final_text(result)
                    if not final_output:
                        final_output = "模型未返回可解析的最终答案，系统已使用回退结果结束。"
                    state.status = "completed"
                    state.final_output = final_output
                    logger.info(
                        "Agent loop completed: step_count=%s",
                        state.step_count,
                    )
                    self._append_trace_event(
                        context=context,
                        state=state,
                        event_type="run_finished",
                        message="Agent run finished.",
                        payload={"step_count": state.step_count},
                    )
                    self._persist_session_messages(context, state)
                    final_result = result.model_copy(
                        update={
                            "run_id": run_id,
                            "session_id": session_id,
                            "step_count": state.step_count,
                            "status": state.status,
                            "final_output": final_output,
                            "reasoning_mode": reasoning_mode,
                            "metrics": self._build_metrics(state, started_at),
                            "trace": list(state.trace_events),
                        }
                    )
                    self._persist_run_metadata(context, state, final_result)
                    return final_result

            return self._build_fallback_final_result(
                context=context,
                state=state,
                started_at=started_at,
                status="max_steps_exceeded",
                message="已达到最大执行步数，系统主动停止以避免死循环。",
                event_type="run_stopped",
            )

    def run_with_plan(
        self,
        *,
        provider: LLMProvider,
        model: str,
        task: str,
        system_prompt: str,
        session_id: str,
        reasoning_mode: str = "default",
        temperature: float = 0.0,
        max_steps: int = 3,
        run_timeout_seconds: int = 120,
        tool_registry: ToolRegistry | None = None,
        session_memory: SessionMemory | None = None,
        summary_memory: SummaryMemory | None = None,
        planner: Planner,
        root_run_id: str | None = None,
    ) -> RunResult:
        """先规划，再顺序执行步骤并汇总结果。"""
        return self.plan_executor.run_with_plan(
            provider=provider,
            model=model,
            task=task,
            system_prompt=system_prompt,
            session_id=session_id,
            reasoning_mode=reasoning_mode,
            temperature=temperature,
            max_steps=max_steps,
            run_timeout_seconds=run_timeout_seconds,
            tool_registry=tool_registry,
            session_memory=session_memory,
            summary_memory=summary_memory,
            planner=planner,
            root_run_id=root_run_id,
        )

    def _build_fallback_final_result(
        self,
        *,
        context: RunContext,
        state: AgentState,
        started_at: float,
        status: str,
        message: str,
        event_type: str,
    ) -> RunResult:
        """构造统一的回退最终结果，避免整个系统崩溃。"""
        state.status = status
        state.final_output = message
        state.fallback_count += 1
        self._append_trace_event(
            context=context,
            state=state,
            event_type="run_failed",
            message=message,
            payload={
                "step_count": state.step_count,
                "reason_event_type": event_type,
                "status": status,
            },
        )
        self._persist_session_messages(context, state)
        fallback_result = RunResult(
            id=f"fallback-final-{context.run_id}",
            model=context.model,
            reasoning_mode=context.reasoning_mode,
            choices=[
                RunChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=message),
                    finish_reason="stop",
                )
            ],
            run_id=context.run_id,
            session_id=context.session_id,
            step_count=state.step_count,
            status=status,
            final_output=message,
            metrics=self._build_metrics(state, started_at),
            trace=list(state.trace_events),
        )
        self._persist_run_metadata(context, state, fallback_result)
        return fallback_result

    def _persist_session_messages(self, context: RunContext, state: AgentState) -> None:
        """持久化当前运行新产生的消息。"""
        if not context.persist_session_memory:
            return
        start_index = 1 + state.history_message_count
        new_messages = [
            message
            for message in state.messages[start_index:]
            if message.role in {"user", "assistant", "tool"}
        ]
        context.session_memory.append(context.session_id, new_messages)
        state.memory_write_count += 1
        self._append_trace_event(
            context=context,
            state=state,
            event_type="memory_written",
            message="Session memory written.",
            payload={"message_count": len(new_messages)},
        )

    def _persist_run_metadata(
        self,
        context: RunContext,
        state: AgentState,
        result: RunResult,
    ) -> None:
        """当仓储支持时，持久化 run 与 trace 元数据。

        trace 事件已在 _append_trace_event 中实时写入 SQLite，
        此处的批量写入是幂等安全网（INSERT OR REPLACE）。
        """
        repository = context.session_memory.repository
        if hasattr(repository, "save_run"):
            repository.save_run(result, state.task)
        if hasattr(repository, "save_trace_events"):
            repository.save_trace_events(context.run_id, state.trace_events)

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
            state.tool_call_count += 1
            logger.info(
                "Executing tool call: step=%s tool=%s tool_call_id=%s",
                state.step_count,
                tool_call.function.name,
                tool_call.id,
            )
            self._append_trace_event(
                context=context,
                state=state,
                event_type="tool_called",
                message="Tool called.",
                payload={
                    "step_count": state.step_count,
                    "tool_name": tool_call.function.name,
                    "tool_call_id": tool_call.id,
                },
            )
            tool_result = context.tool_registry.execute_tool_call(tool_call)
            state.messages.append(tool_result.to_message())
            if tool_result.is_error:
                state.tool_error_count += 1
                logger.error(
                    "Tool call failed: step=%s tool=%s tool_call_id=%s",
                    state.step_count,
                    tool_result.name,
                    tool_result.tool_call_id,
                )
            else:
                state.last_successful_tool_result = tool_result
                logger.info(
                    "Tool call completed: step=%s tool=%s tool_call_id=%s",
                    state.step_count,
                    tool_result.name,
                    tool_result.tool_call_id,
                )
            self._append_trace_event(
                context=context,
                state=state,
                event_type="tool_result",
                message="Tool result received.",
                payload={
                    "step_count": state.step_count,
                    "tool_name": tool_result.name,
                    "tool_call_id": tool_result.tool_call_id,
                    "is_error": tool_result.is_error,
                },
            )

    def _handle_hallucinated_tool_calls_without_registry(
        self,
        *,
        context: RunContext,
        state: AgentState,
        started_at: float,
        result: RunResult,
        reasoning_mode: str,
    ) -> RunResult:
        """在当前步骤未暴露任何工具时，硬拦截 hallucinated tool calls。"""
        tool_calls = extract_tool_calls(result)
        self._append_trace_event(
            context=context,
            state=state,
            event_type="tool_call_ignored",
            message="Hallucinated tool calls were intercepted because no tools are available.",
            payload={
                "step_count": state.step_count,
                "tool_count": len(tool_calls),
            },
        )
        assistant_message = result.choices[0].message
        if assistant_message.content and assistant_message.content.strip():
            sanitized_message = assistant_message.model_copy(update={"tool_calls": []})
            state.messages.append(sanitized_message)
            state.status = "completed"
            state.final_output = assistant_message.content.strip()
            self._append_trace_event(
                context=context,
                state=state,
                event_type="run_finished",
                message="Agent run finished after intercepting hallucinated tool calls.",
                payload={"step_count": state.step_count},
            )
            self._persist_session_messages(context, state)
            final_result = result.model_copy(
                update={
                    "run_id": context.run_id,
                    "session_id": context.session_id,
                    "step_count": state.step_count,
                    "status": state.status,
                    "final_output": state.final_output,
                    "reasoning_mode": reasoning_mode,
                    "choices": [
                        RunChoice(
                            index=choice.index,
                            message=sanitized_message if choice.index == 0 else choice.message,
                            finish_reason=choice.finish_reason,
                        )
                        for choice in result.choices
                    ],
                    "metrics": self._build_metrics(state, started_at),
                    "trace": list(state.trace_events),
                }
            )
            self._persist_run_metadata(context, state, final_result)
            return final_result
        return self._build_fallback_final_result(
            context=context,
            state=state,
            started_at=started_at,
            status="failed",
            message="当前步骤未暴露任何工具，但模型仍然发起了 tool call；系统已拦截该无效调用。",
            event_type="tool_call_ignored",
        )

    def _build_timeout_result(
        self,
        *,
        context: RunContext,
        state: AgentState,
        started_at: float,
    ) -> RunResult:
        partial_message = self._build_partial_timeout_message(context=context, state=state)
        if partial_message is not None:
            return self._build_fallback_final_result(
                context=context,
                state=state,
                started_at=started_at,
                status="partial_completed",
                message=partial_message,
                event_type="run_timeout",
            )
        return self._build_fallback_final_result(
            context=context,
            state=state,
            started_at=started_at,
            status="failed",
            message=f"运行超时，已在 {context.run_timeout_seconds} 秒后停止。",
            event_type="run_timeout",
        )

    def _build_partial_timeout_message(
        self,
        *,
        context: RunContext,
        state: AgentState,
    ) -> str | None:
        tool_result = state.last_successful_tool_result
        if tool_result is None or tool_result.is_error or tool_result.name != "write_file":
            return None
        payload = self._parse_tool_result_payload(tool_result)
        if payload is None:
            return None
        if payload.get("ok") is not True or payload.get("dry_run") is True:
            return None
        raw_path = payload.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return None
        display_path = raw_path.strip()
        try:
            resolved_path = context.tool_registry.workspace_root.joinpath(display_path).resolve()
            if resolved_path.is_file():
                display_path = str(resolved_path.relative_to(context.tool_registry.workspace_root.resolve()))
        except Exception:
            pass
        created = payload.get("created")
        created_message = "新建" if created is True else "更新"
        return (
            "本次运行在超时前已完成部分工作。"
            f" 已通过 `write_file` 成功{created_message}文件：{display_path}。"
            " 但后续总结阶段未完成，因此当前返回的是部分完成摘要，而不是完整最终答案。"
        )

    def _parse_tool_result_payload(self, tool_result) -> dict[str, object] | None:
        try:
            payload = json.loads(tool_result.content)
        except (TypeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _append_trace_event(
        self,
        *,
        context: RunContext,
        state: AgentState,
        event_type: str,
        message: str,
        payload: dict[str, object] | None = None,
    ) -> None:
        """统一追加并落盘 Trace 事件。

        写入顺序：SQLite（权威数据源）→ JSONL（辅助 debug 日志）。
        SQLite 写入失败仅记录警告，不影响运行；JSONL 作为备份仍会写入，
        后续可通过 reconcile_from_jsonl 恢复缺失数据。
        """
        event = make_trace_event(
            run_id=context.run_id,
            root_run_id=context.root_run_id,
            parent_run_id=context.parent_run_id,
            session_id=context.session_id,
            event_type=event_type,
            message=message,
            payload=payload,
        )
        state.trace_events.append(event)
        # SQLite 是权威数据源，优先写入
        sqlite_ok = context.trace_repository.save_event(context.run_id, event)
        if not sqlite_ok:
            logger.warning(
                "Trace event not persisted to SQLite, JSONL is the fallback: "
                "run_id=%s event_type=%s",
                context.run_id,
                event_type,
            )
        # JSONL 是辅助 debug 日志，后写入（即使 SQLite 失败也写 JSONL 作为备份）
        context.trace_recorder.record(event)

    def _build_metrics(self, state: AgentState, started_at: float) -> RunMetrics:
        """根据当前状态构造运行指标。"""
        return RunMetrics(
            duration_seconds=max(monotonic() - started_at, 0.0),
            llm_call_count=state.llm_call_count,
            tool_call_count=state.tool_call_count,
            tool_error_count=state.tool_error_count,
            memory_write_count=state.memory_write_count,
            fallback_count=state.fallback_count,
        )
