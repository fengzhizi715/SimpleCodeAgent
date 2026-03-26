"""Trace SQLite 仓储。"""

from __future__ import annotations

import json

from app.contracts.trace import TraceEvent
from app.db.sqlite import SQLiteDB


class SQLiteTraceRepository:
    """负责 Trace 元数据的 SQLite 持久化与查询。"""

    def __init__(self, db: SQLiteDB) -> None:
        self.db = db

    def save_events(self, run_id: str, events: list[TraceEvent]) -> None:
        """持久化某次运行的全部事件。"""
        self.db.executemany(
            """
            INSERT OR REPLACE INTO trace_index (
                id, run_id, event_type, message, payload_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    event.id,
                    run_id,
                    event.event_type,
                    event.message,
                    json.dumps(event.payload, ensure_ascii=False),
                    event.created_at,
                )
                for event in events
            ],
        )

    def query_timeline(self, run_id: str) -> list[TraceEvent]:
        """按时间顺序查询某次运行的 timeline。"""
        rows = self.db.fetchall(
            """
            SELECT id, run_id, event_type, message, payload_json, created_at
            FROM trace_index
            WHERE run_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (run_id,),
        )
        events: list[TraceEvent] = []
        for row in rows:
            payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
            events.append(
                TraceEvent.model_validate(
                    {
                        "id": row["id"],
                        "run_id": row["run_id"],
                        "event_type": row["event_type"],
                        "message": row["message"],
                        "created_at": row["created_at"],
                        "payload": payload,
                    }
                )
            )
        return events
