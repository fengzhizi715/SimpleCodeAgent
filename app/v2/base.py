"""V2 Agent 基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from app.contracts.agent import AgentResult, AgentSpec, AgentTask, SharedWorkspace
from app.contracts.trace import TraceEvent
from app.llm.client import LLMProvider
from app.trace.recorder import JsonlTraceRecorder
from app.trace.repository import SQLiteTraceRepository
from app.v1.tools.registry import ToolRegistry


class AgentContext:
    """V2 Agent 执行上下文。"""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        model: str,
        reasoning_mode: str,
        tool_registry: ToolRegistry,
        trace_repository: SQLiteTraceRepository,
        trace_recorder: JsonlTraceRecorder,
        workspace_root: Path,
        session_id: str,
        run_id: str,
    ) -> None:
        self.provider = provider
        self.model = model
        self.reasoning_mode = reasoning_mode
        self.tool_registry = tool_registry
        self.trace_repository = trace_repository
        self.trace_recorder = trace_recorder
        self.workspace_root = workspace_root
        self.session_id = session_id
        self.run_id = run_id


class OrchestratorDelegationClient:
    """只提供给 orchestrator 的委派客户端。"""

    def __init__(self, delegate_fn: Callable[..., AgentResult]) -> None:
        self._delegate_fn = delegate_fn

    def delegate(
        self,
        *,
        agent_id: str,
        task: AgentTask,
        workspace: SharedWorkspace,
        context: AgentContext,
        trace_events: list[TraceEvent],
        delegation_records: list,
        delegation_start_event_ids: dict[str, str],
        parent_event_id: str | None = None,
    ) -> AgentResult:
        return self._delegate_fn(
            agent_id=agent_id,
            task=task,
            workspace=workspace,
            context=context,
            trace_events=trace_events,
            delegation_records=delegation_records,
            delegation_start_event_ids=delegation_start_event_ids,
            parent_event_id=parent_event_id,
        )


class AgentBase(ABC):
    """所有 V2 Agent 的抽象基类。"""

    __test__ = False

    def __init__(self, spec: AgentSpec) -> None:
        self.spec = spec

    @abstractmethod
    def run(
        self,
        *,
        task: AgentTask,
        workspace: SharedWorkspace,
        context: AgentContext,
        prompt_context: dict[str, object],
    ) -> AgentResult:
        """执行结构化任务并返回结果。"""

    def build_trace_event(
        self,
        *,
        event_type: str,
        message: str,
        context: AgentContext,
        task: AgentTask,
        status: str | None = None,
        input_summary: str | None = None,
        output_summary: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> TraceEvent:
        """为当前 Agent 任务创建标准 Trace 事件。"""
        timestamp = datetime.now(UTC).isoformat()
        return TraceEvent(
            run_id=context.run_id,
            root_run_id=context.run_id,
            session_id=context.session_id,
            actor=self.spec.agent_id,
            action=task.step_type,
            status=status,
            input_summary=input_summary,
            output_summary=output_summary,
            started_at=timestamp,
            ended_at=timestamp,
            event_type=event_type,
            message=message,
            payload={
                "task_id": task.task_id,
                "step_id": task.step_id,
                "target_agent": task.target_agent,
                **(payload or {}),
            },
        )
