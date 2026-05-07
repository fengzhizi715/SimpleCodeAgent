"""Trace 展示器。"""

from __future__ import annotations

import json

from app.contracts.trace import TraceEvent
from app.trace.repository import SQLiteTraceRepository


def format_timeline(events: list[TraceEvent]) -> str:
    """将事件时间线格式化为可读文本。"""
    lines: list[str] = []
    for event in events:
        payload = json.dumps(event.payload, ensure_ascii=False, sort_keys=True)
        lines.append(
            f"[{event.created_at}] {event.event_type} | run_id={event.run_id} | {event.message} | payload={payload}"
        )
    return "\n".join(lines)


def load_and_format_timeline(repository: SQLiteTraceRepository, run_id: str) -> str:
    """按 run_id 加载并格式化时间线。"""
    events = repository.query_timeline(run_id)
    if not events:
        raise ValueError(f"未找到 run_id={run_id} 的 trace。")
    return format_timeline(events)


def load_and_format_root_timeline(repository: SQLiteTraceRepository, root_run_id: str) -> str:
    """按 root_run_id 加载并格式化整棵运行树时间线。"""
    events = repository.query_timeline_by_root(root_run_id)
    if not events:
        raise ValueError(f"未找到 root_run_id={root_run_id} 的 trace。")
    return format_timeline(events)


def load_and_format_session_timeline(repository: SQLiteTraceRepository, session_id: str) -> str:
    """按 session_id 加载并格式化整段会话时间线。"""
    events = repository.query_timeline_by_session(session_id)
    if not events:
        raise ValueError(f"未找到 session_id={session_id} 的 trace。")
    return format_timeline(events)
