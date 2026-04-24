"""基于 SQLite 的 Memory 仓储实现。"""

from __future__ import annotations

import json
from pathlib import Path

from app.contracts.message import ChatMessage
from app.contracts.run import RunResult
from app.contracts.trace import TraceEvent
from app.core.logger import get_logger
from app.db.sqlite import SQLiteDB
from app.v1.memory.base import MemoryRepository
from app.trace.repository import SQLiteTraceRepository

logger = get_logger(__name__)


class SQLiteMemoryRepository(MemoryRepository):
    """使用 SQLite 持久化会话记忆。"""

    _cleanup_ran: bool = False

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db = SQLiteDB(db_path)
        logger.info("Initialized SQLite memory repository: db_path=%s", self.db.db_path)
        self._maybe_cleanup_old_sessions()

    def get_session_messages(self, session_id: str, limit: int) -> list[ChatMessage]:
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

        messages: list[ChatMessage] = []
        for row in reversed(rows):
            tool_calls = json.loads(row["tool_calls_json"]) if row["tool_calls_json"] else []
            messages.append(
                ChatMessage.model_validate(
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

    def append_session_messages(self, session_id: str, messages: list[ChatMessage]) -> None:
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

    def save_run(
        self,
        run: RunResult,
        task: str,
        *,
        is_top_level: bool = True,
        parent_run_id: str | None = None,
    ) -> None:
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
                run_id, session_id, model, task, is_top_level, parent_run_id, status, step_count, final_output,
                created_at, updated_at, agent_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'v1')
            ON CONFLICT(run_id) DO UPDATE SET
                session_id = excluded.session_id,
                model = excluded.model,
                task = excluded.task,
                is_top_level = excluded.is_top_level,
                parent_run_id = excluded.parent_run_id,
                status = excluded.status,
                step_count = excluded.step_count,
                final_output = excluded.final_output,
                agent_version = 'v1',
                updated_at = excluded.updated_at
            """,
            (
                run.run_id,
                run.session_id,
                run.model,
                task,
                1 if is_top_level else 0,
                parent_run_id,
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

    def cleanup_old_sessions(self, max_age_days: int = 30) -> int:
        """清理超过指定天数的会话及其关联数据。

        按级联顺序删除：trace_index → runs → messages → summaries → sessions，
        最后执行 VACUUM 压缩数据库文件。

        Args:
            max_age_days: 保留最近多少天的会话，默认 30 天。

        Returns:
            被清理的会话数量。
        """
        from datetime import datetime, timedelta, timezone

        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()

        # 查找过期的 session_id
        old_sessions = self.db.fetchall(
            "SELECT id FROM sessions WHERE updated_at < ?",
            (cutoff,),
        )
        if not old_sessions:
            return 0

        session_ids = [row["id"] for row in old_sessions]

        # 批量删除关联数据（使用子查询避免逐条循环）
        # 1. 删除 trace_index（通过 runs 关联）
        placeholders = ",".join("?" for _ in session_ids)
        self.db.execute(
            f"DELETE FROM trace_index WHERE run_id IN "
            f"(SELECT run_id FROM runs WHERE session_id IN ({placeholders}))",
            tuple(session_ids),
        )
        # 2. 删除 runs
        self.db.execute(
            f"DELETE FROM runs WHERE session_id IN ({placeholders})",
            tuple(session_ids),
        )
        # 3. 删除 messages
        self.db.execute(
            f"DELETE FROM messages WHERE session_id IN ({placeholders})",
            tuple(session_ids),
        )
        # 4. 删除 summaries
        self.db.execute(
            f"DELETE FROM summaries WHERE session_id IN ({placeholders})",
            tuple(session_ids),
        )
        # 5. 删除 sessions
        self.db.executemany(
            "DELETE FROM sessions WHERE id = ?",
            [(session_id,) for session_id in session_ids],
        )

        # 压缩数据库文件
        # VACUUM 不能在事务内执行，需要直接使用连接对象
        try:
            conn = self.db.connect()
            conn.execute("VACUUM")
        except Exception:
            logger.warning("VACUUM failed after cleanup, database will continue to work but file may be larger")

        logger.info(
            "Cleaned up old sessions: count=%s max_age_days=%s",
            len(session_ids),
            max_age_days,
        )
        return len(session_ids)

    def _maybe_cleanup_old_sessions(self) -> None:
        """在仓储初始化时执行一次默认清理，形成基础保留策略。"""
        if self.__class__._cleanup_ran:
            return
        try:
            cleaned = self.cleanup_old_sessions(max_age_days=30)
            logger.info(
                "Applied default session retention policy: cleaned=%s max_age_days=30",
                cleaned,
            )
        finally:
            self.__class__._cleanup_ran = True

    def save_trace_events(self, run_id: str, events: list[TraceEvent]) -> bool:
        """持久化某次运行的追踪元数据。

        Returns:
            True 表示写入成功，False 表示写入失败。
        """
        result = SQLiteTraceRepository(self.db).save_events(run_id, events)
        if result:
            logger.info("Persisted trace events: run_id=%s event_count=%s", run_id, len(events))
        else:
            logger.warning("Failed to persist trace events to SQLite: run_id=%s event_count=%s", run_id, len(events))
        return result
