"""最小 Agent 循环。"""

from __future__ import annotations

from time import monotonic
from uuid import uuid4

from app.contracts.message import Message
from app.contracts.planner import PlanStep
from app.contracts.run import RunChoice, RunResult
from app.contracts.trace import TraceEvent
from app.core.exceptions import AppError, RuntimeMaxStepsError, RuntimeTimeoutError
from app.llm.client import LLMProvider
from app.llm.parser import extract_final_text, extract_tool_calls
from app.trace.events import make_trace_event
from app.trace.recorder import JsonlTraceRecorder
from app.trace.repository import SQLiteTraceRepository
from app.v1.memory.repository import SQLiteMemoryRepository
from app.v1.memory.session_memory import SessionMemory
from app.v1.memory.summary_memory import SummaryMemory
from app.v1.planner.base import Planner
from app.v1.runtime.context import RunContext
from app.v1.runtime.executor import RuntimeExecutor
from app.v1.runtime.state import AgentState
from app.v1.tools.registry import ToolRegistry


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
        run_timeout_seconds: int = 120,
        tool_registry: ToolRegistry | None = None,
        session_memory: SessionMemory | None = None,
        summary_memory: SummaryMemory | None = None,
        persist_session_memory: bool = True,
    ) -> RunResult:
        """执行最小 Agent 循环并返回标准化结果。"""
        run_id = str(uuid4())
        started_at = monotonic()
        registry = tool_registry or ToolRegistry()
        session_store = session_memory or SessionMemory(SQLiteMemoryRepository())
        summary_store = summary_memory or SummaryMemory(session_store.repository)
        trace_repository = SQLiteTraceRepository(session_store.repository.db)
        trace_recorder = JsonlTraceRecorder(run_id=run_id)
        history_messages = session_store.load(session_id)
        # RunContext 集中持有本次执行依赖，避免 loop 中散落太多环境判断。
        context = RunContext(
            run_id=run_id,
            session_id=session_id,
            provider=provider,
            model=model,
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
            messages=[
                # 每次运行都重新注入增强后的 system prompt，确保工具约束和编程规则生效。
                Message(role="system", content=context.effective_system_prompt),
                *history_messages,
                Message(role="user", content=task),
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

        while state.step_count < context.max_steps:
            # 这里控制的是“整次运行”的总时长。
            # 单次 LLM 请求的超时由 Provider 层处理，Runtime 只负责全局兜底停止。
            if monotonic() - started_at >= context.run_timeout_seconds:
                return self._build_fallback_final_result(
                    context=context,
                    state=state,
                    status="failed",
                    message=f"运行超时，已在 {context.run_timeout_seconds} 秒后停止。",
                    event_type="run_timeout",
                )

            state.step_count += 1
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
            result = self.executor.execute(context, state)
            if not result.choices:
                return self._build_fallback_final_result(
                    context=context,
                    state=state,
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
                # 先记录 assistant 的 tool-call 消息，再把工具结果回填给下一轮模型。
                assistant_message = result.choices[0].message
                state.messages.append(assistant_message)
                self._handle_tool_calls(
                    tool_calls=tool_calls,
                    context=context,
                    state=state,
                )
                continue

            if result.status == "failed":
                return self._build_fallback_final_result(
                    context=context,
                    state=state,
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
                        "trace": list(state.trace_events),
                    }
                )
                self._persist_run_metadata(context, state, final_result)
                return final_result

        return self._build_fallback_final_result(
            context=context,
            state=state,
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
        temperature: float = 0.0,
        max_steps: int = 3,
        run_timeout_seconds: int = 120,
        tool_registry: ToolRegistry | None = None,
        session_memory: SessionMemory | None = None,
        summary_memory: SummaryMemory | None = None,
        planner: Planner,
    ) -> RunResult:
        """先规划，再顺序执行步骤并汇总结果。"""
        plan = planner.create_plan(task)
        if not plan:
            return self.run(
                provider=provider,
                model=model,
                task=task,
                system_prompt=system_prompt,
                session_id=session_id,
                temperature=temperature,
                max_steps=max_steps,
                run_timeout_seconds=run_timeout_seconds,
                tool_registry=tool_registry,
                session_memory=session_memory,
                summary_memory=summary_memory,
            )

        step_outputs: list[str] = []
        total_step_count = 0
        plan_failed = False

        for index, step in enumerate(plan, start=1):
            step_result = self._run_plan_step(
                provider=provider,
                model=model,
                task=task,
                system_prompt=system_prompt,
                session_id=session_id,
                temperature=temperature,
                max_steps=max_steps,
                run_timeout_seconds=run_timeout_seconds,
                tool_registry=tool_registry,
                session_memory=session_memory,
                summary_memory=summary_memory,
                step=step,
                step_index=index,
                total_steps=len(plan),
                previous_outputs=step_outputs,
            )
            step_outputs.append(step_result.final_output)
            total_step_count += step_result.step_count
            if step.status == "failed":
                plan_failed = True
                break

        summary_prompt = self._build_summary_prompt(task=task, plan=plan, step_outputs=step_outputs)
        summary_result = self.run(
            provider=provider,
            model=model,
            task=summary_prompt,
            system_prompt=system_prompt,
            session_id=session_id,
            temperature=temperature,
            max_steps=max_steps,
            run_timeout_seconds=run_timeout_seconds,
            tool_registry=tool_registry,
            session_memory=session_memory,
            summary_memory=summary_memory,
            persist_session_memory=False,
        )
        # 规划步骤和汇总步骤不直接写入会话记忆，避免把中间推理污染成长期上下文。
        if session_memory is not None and summary_result.status == "completed":
            session_memory.append(
                session_id,
                [
                    Message(role="user", content=task),
                    Message(role="assistant", content=summary_result.final_output),
                ],
            )
        return summary_result.model_copy(
            update={
                "session_id": session_id,
                "step_count": total_step_count + summary_result.step_count,
                "plan": plan,
                "status": "failed" if plan_failed else summary_result.status,
            }
        )

    def _build_fallback_final_result(
        self,
        *,
        context: RunContext,
        state: AgentState,
        status: str,
        message: str,
        event_type: str,
    ) -> RunResult:
        """构造统一的回退最终结果，避免整个系统崩溃。"""
        state.status = status
        state.final_output = message
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
            choices=[
                RunChoice(
                    index=0,
                    message=Message(role="assistant", content=message),
                    finish_reason="stop",
                )
            ],
            run_id=context.run_id,
            session_id=context.session_id,
            step_count=state.step_count,
            status=status,
            final_output=message,
            trace=list(state.trace_events),
        )
        self._persist_run_metadata(context, state, fallback_result)
        return fallback_result

    def _persist_session_messages(self, context: RunContext, state: AgentState) -> None:
        """持久化当前运行新产生的消息。"""
        if not context.persist_session_memory:
            return
        start_index = 1 + state.history_message_count
        # 这里只保存本轮新增消息，避免把已加载的历史重复写回数据库。
        new_messages = [
            message
            for message in state.messages[start_index:]
            if message.role in {"user", "assistant", "tool"}
        ]
        context.session_memory.append(context.session_id, new_messages)
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
        """当仓储支持时，持久化 run 与 trace 元数据。"""
        repository = context.session_memory.repository
        if hasattr(repository, "save_run"):
            repository.save_run(result, state.task)
        if hasattr(repository, "save_trace_events"):
            repository.save_trace_events(context.run_id, state.trace_events)

    def _run_plan_step(
        self,
        *,
        provider: LLMProvider,
        model: str,
        task: str,
        system_prompt: str,
        session_id: str,
        temperature: float,
        max_steps: int,
        run_timeout_seconds: int,
        tool_registry: ToolRegistry | None,
        session_memory: SessionMemory | None,
        summary_memory: SummaryMemory | None,
        step: PlanStep,
        step_index: int,
        total_steps: int,
        previous_outputs: list[str],
    ) -> RunResult:
        """执行单个规划步骤，并按需要重试。"""
        last_result: RunResult | None = None
        total_attempts = max(1, step.max_retries + 1)

        for attempt_index in range(total_attempts):
            # 每个规划步骤都作为独立 run 执行，方便追踪和重试；
            # 但它们仍然共享同一个 session，保证同任务上下文不被切碎。
            step.status = "in_progress"
            step.retry_count = attempt_index
            step_prompt = self._build_step_prompt(
                task=task,
                step=step,
                step_index=step_index,
                total_steps=total_steps,
                previous_outputs=previous_outputs,
            )
            last_result = self.run(
                provider=provider,
                model=model,
                task=step_prompt,
                system_prompt=system_prompt,
                session_id=session_id,
                temperature=temperature,
                max_steps=max_steps,
                run_timeout_seconds=run_timeout_seconds,
                tool_registry=tool_registry,
                session_memory=session_memory,
                summary_memory=summary_memory,
                persist_session_memory=False,
            )
            step.output_summary = last_result.final_output
            if last_result.status == "completed":
                step.status = "completed"
                return last_result

        step.status = "failed"
        return last_result or RunResult(
            id="planner-step-fallback",
            model=model,
            choices=[],
            session_id=session_id,
            status="failed",
            final_output=f"步骤执行失败：{step.title}",
        )

    def _build_step_prompt(
        self,
        *,
        task: str,
        step: PlanStep,
        step_index: int,
        total_steps: int,
        previous_outputs: list[str],
    ) -> str:
        """构造单个规划步骤的执行提示。"""
        sections = [
            f"总任务：{task}",
            f"当前是第 {step_index}/{total_steps} 步。",
            f"步骤标题：{step.title}",
            f"步骤描述：{step.description}",
        ]
        if step.input_summary:
            sections.append(f"输入摘要：{step.input_summary}")
        if previous_outputs:
            sections.append("前序步骤结果：")
            sections.extend(
                [f"- 第 {index + 1} 步：{output}" for index, output in enumerate(previous_outputs)]
            )
        sections.append("请只完成当前步骤，并输出该步骤的结果。")
        return "\n".join(sections)

    def _build_summary_prompt(
        self,
        *,
        task: str,
        plan: list[PlanStep],
        step_outputs: list[str],
    ) -> str:
        """构造最终汇总提示。"""
        lines = [f"请基于以下步骤结果，汇总完成总任务：{task}", "步骤结果："]
        for index, step in enumerate(plan, start=1):
            lines.append(f"{index}. {step.title}")
            if step.status == "failed":
                lines.append(f"步骤失败：{step.output_summary or '无输出'}")
                continue
            if index <= len(step_outputs):
                lines.append(step_outputs[index - 1])
        lines.append("请输出最终完整答案。")
        return "\n".join(lines)

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
            # 无论工具成功还是失败，都统一转成 tool 消息回填给模型。
            # 这样模型可以自己决定是重试、换工具，还是直接向用户解释问题。
            state.messages.append(tool_result.to_message())
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

    def _append_trace_event(
        self,
        *,
        context: RunContext,
        state: AgentState,
        event_type: str,
        message: str,
        payload: dict[str, object] | None = None,
    ) -> None:
        """统一追加并落盘 Trace 事件。"""
        event = make_trace_event(
            run_id=context.run_id,
            session_id=context.session_id,
            event_type=event_type,
            message=message,
            payload=payload,
        )
        state.trace_events.append(event)
        context.trace_recorder.record(event)
