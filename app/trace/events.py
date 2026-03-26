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
]


def make_trace_event(
    *,
    run_id: str,
    session_id: str,
    event_type: TraceEventType,
    message: str,
    payload: dict[str, object] | None = None,
) -> TraceEvent:
    """创建标准 TraceEvent。"""
    return TraceEvent(
        run_id=run_id,
        session_id=session_id,
        event_type=event_type,
        message=message,
        payload=payload or {},
    )
