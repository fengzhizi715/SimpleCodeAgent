"""Trace 查询接口。"""

from __future__ import annotations

from pathlib import Path

from app.db.sqlite import SQLiteDB
from app.trace.repository import SQLiteTraceRepository


def query_trace_timeline(run_id: str, db_path: str | Path | None = None) -> list[dict[str, object]]:
    """按 run_id 查询 Trace 时间线，供 API 层复用。"""
    repository = SQLiteTraceRepository(SQLiteDB(db_path))
    return [event.model_dump() for event in repository.query_timeline(run_id)]
