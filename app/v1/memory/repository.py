"""基于 SQLite 的 Memory 仓储实现。"""

from __future__ import annotations

import json
from pathlib import Path

from app.contracts.message import Message
from app.contracts.run import RunResult
from app.contracts.trace import TraceEvent
from app.core.logger import get_logger
from app.db.sqlite import SQLiteDB
from app.v1.memory.base import MemoryRepository
from app.trace.repository import SQLiteTraceRepository

logger = get_logger(__name__)


class SQLiteMemoryRepository(MemoryRepository):
    """使用 SQLite 持久化会话记忆。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db = SQLiteDB(db_path)
        logger.info("Initialized SQLite memory repository: db_path=%s", self.db.db_path)

    def get_session_messages(self, session_id: str, limit: int) -> list[Message]:
        rows = self.db.fetchall(
            """
            SELECT role, content, name, tool_call_id, tool_calls_json
            FROM messages
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit),
        )

        messages: list[Message] = []
        for row in reversed(rows):
            tool_calls = json.loads(row["tool_calls_json"]) if row["tool_calls_json"] else []
            messages.append(
                Message.model_validate(
                    {
                        "role": row["role"],
                        "content": row["content"],
                        "name": row["name"],
                        "tool_call_id": row["tool_call_id"],
                        "tool_calls": tool_calls,
                    }
                )
            )
        return messages

    def append_session_messages(self, session_id: str, messages: list[Message]) -> None:
        if not messages:
            return

        timestamp = self.db.now()
        self.db.execute(
            """
            INSERT INTO sessions (id, created_at, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (session_id, timestamp, timestamp),
        )
        self.db.executemany(
            """
            INSERT INTO messages (
                session_id, role, content, name, tool_call_id, tool_calls_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    session_id,
                    message.role,
                    message.content,
                    message.name,
                    message.tool_call_id,
                    json.dumps(
                        [tool_call.model_dump() for tool_call in message.tool_calls],
                        ensure_ascii=False,
                    ),
                    timestamp,
                )
                for message in messages
            ],
        )
        logger.info(
            "Persisted session messages: session_id=%s message_count=%s",
            session_id,
            len(messages),
        )

    def get_summary(self, session_id: str) -> str | None:
        row = self.db.fetchone(
            "SELECT summary FROM summaries WHERE session_id = ?",
            (session_id,),
        )
        return None if row is None else row["summary"]

    def save_summary(self, session_id: str, summary: str) -> None:
        timestamp = self.db.now()
        self.db.execute(
            """
            INSERT INTO summaries (session_id, summary, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                summary = excluded.summary,
                updated_at = excluded.updated_at
            """,
            (session_id, summary, timestamp),
        )

    def save_run(self, run: RunResult, task: str) -> None:
        """持久化运行元数据。"""
        timestamp = self.db.now()
        self.db.execute(
            """
            INSERT INTO sessions (id, created_at, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (run.session_id, timestamp, timestamp),
        )
        self.db.execute(
            """
            INSERT INTO runs (
                run_id, session_id, model, task, status, step_count, final_output, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                status = excluded.status,
                step_count = excluded.step_count,
                final_output = excluded.final_output,
                updated_at = excluded.updated_at
            """,
            (
                run.run_id,
                run.session_id,
                run.model,
                task,
                run.status,
                run.step_count,
                run.final_output,
                timestamp,
                timestamp,
            ),
        )
        logger.info(
            "Persisted run metadata: run_id=%s session_id=%s status=%s step_count=%s",
            run.run_id,
            run.session_id,
            run.status,
            run.step_count,
        )

    def save_trace_events(self, run_id: str, events: list[TraceEvent]) -> None:
        """持久化某次运行的追踪元数据。"""
        SQLiteTraceRepository(self.db).save_events(run_id, events)
        logger.info("Persisted trace events: run_id=%s event_count=%s", run_id, len(events))
