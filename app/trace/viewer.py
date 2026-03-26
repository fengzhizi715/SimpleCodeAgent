"""Trace 展示器。"""

from __future__ import annotations

import json

from app.contracts.trace import TraceEvent


def format_timeline(events: list[TraceEvent]) -> str:
    """将事件时间线格式化为可读文本。"""
    lines: list[str] = []
    for event in events:
        payload = json.dumps(event.payload, ensure_ascii=False, sort_keys=True)
        lines.append(
            f"[{event.created_at}] {event.event_type} | run_id={event.run_id} | {event.message} | payload={payload}"
        )
    return "\n".join(lines)
