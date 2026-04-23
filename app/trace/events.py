"""Trace 事件定义。"""

from __future__ import annotations

from typing import Literal

from app.contracts.trace import TraceEvent

TraceEventType = Literal[
    "run_started",
    "llm_called",
    "llm_responded",
    "tool_called",
    "tool_result",
    "memory_written",
    "run_finished",
    "run_failed",
    "step_started",
    "agent_selected",
    "delegation_started",
    "delegation_finished",
    "workspace_updated",
    "replan_started",
    "replan_finished",
    "fallback_triggered",
]


def make_trace_event(
    *,
    run_id: str,
    root_run_id: str | None = None,
    parent_run_id: str | None = None,
    session_id: str,
    event_type: TraceEventType,
    message: str,
    payload: dict[str, object] | None = None,
) -> TraceEvent:
    """创建标准 TraceEvent。"""
    return TraceEvent(
        run_id=run_id,
        root_run_id=root_run_id,
        parent_run_id=parent_run_id,
        session_id=session_id,
        event_type=event_type,
        message=message,
        payload=payload or {},
    )
