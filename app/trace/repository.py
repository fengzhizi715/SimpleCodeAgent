"""Trace SQLite 仓储（权威数据源）。"""

from __future__ import annotations

import json
from pathlib import Path

from app.contracts.trace import TraceEvent
from app.core.logger import get_logger
from app.db.sqlite import SQLiteDB

logger = get_logger(__name__)


class SQLiteTraceRepository:
    """负责 Trace 元数据的 SQLite 持久化与查询。

    SQLite 是 trace 的权威数据源，JSONL 是辅助 debug 日志。
    写入顺序应为：先 SQLite → 再 JSONL，确保权威数据优先落盘。
    """

    def __init__(self, db: SQLiteDB) -> None:
        self.db = db

    def save_event(self, run_id: str, event: TraceEvent) -> bool:
        """持久化单个 Trace 事件（用于实时写入，保证 SQLite 优先落盘）。

        Returns:
            True 表示写入成功，False 表示写入失败（JSONL 可作为恢复源）。
        """
        payload = dict(event.payload)
        try:
            self._ensure_run_exists(run_id=run_id, session_id=event.session_id)
            self.db.execute(
                """
                INSERT OR REPLACE INTO trace_index (
                    id,
                    run_id,
                    session_id,
                    root_run_id,
                    parent_run_id,
                    parent_event_id,
                    actor,
                    action,
                    status,
                    input_summary,
                    output_summary,
                    event_type,
                    message,
                    payload_json,
                    started_at,
                    ended_at,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    run_id,
                    event.session_id,
                    event.root_run_id,
                    event.parent_run_id,
                    event.parent_event_id,
                    event.actor,
                    event.action,
                    event.status,
                    event.input_summary,
                    event.output_summary,
                    event.event_type,
                    event.message,
                    json.dumps(payload, ensure_ascii=False),
                    event.started_at,
                    event.ended_at,
                    event.created_at,
                ),
            )
            return True
        except Exception:
            logger.warning(
                "SQLite trace save_event failed (JSONL may still have data): "
                "run_id=%s event_type=%s event_id=%s",
                run_id,
                event.event_type,
                event.id,
            )
            return False

    def save_events(self, run_id: str, events: list[TraceEvent]) -> bool:
        """持久化某次运行的全部事件（批量写入，作为实时写入的幂等安全网）。

        Returns:
            True 表示全部写入成功，False 表示写入失败。
        """
        def build_payload(event: TraceEvent) -> str:
            return json.dumps(dict(event.payload), ensure_ascii=False)

        try:
            self._ensure_run_exists(
                run_id=run_id,
                session_id=events[0].session_id if events else None,
            )
            self.db.executemany(
                """
                INSERT OR REPLACE INTO trace_index (
                    id,
                    run_id,
                    session_id,
                    root_run_id,
                    parent_run_id,
                    parent_event_id,
                    actor,
                    action,
                    status,
                    input_summary,
                    output_summary,
                    event_type,
                    message,
                    payload_json,
                    started_at,
                    ended_at,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        event.id,
                        run_id,
                        event.session_id,
                        event.root_run_id,
                        event.parent_run_id,
                        event.parent_event_id,
                        event.actor,
                        event.action,
                        event.status,
                        event.input_summary,
                        event.output_summary,
                        event.event_type,
                        event.message,
                        build_payload(event),
                        event.started_at,
                        event.ended_at,
                        event.created_at,
                    )
                    for event in events
                ],
            )
            return True
        except Exception:
            logger.warning(
                "SQLite trace save_events batch failed (JSONL may still have data): "
                "run_id=%s count=%s",
                run_id,
                len(events),
            )
            return False

    def query_timeline(self, run_id: str) -> list[TraceEvent]:
        """按时间顺序查询某次运行的 timeline。"""
        rows = self.db.fetchall(
            """
            SELECT
                id,
                run_id,
                session_id,
                root_run_id,
                parent_run_id,
                parent_event_id,
                actor,
                action,
                status,
                input_summary,
                output_summary,
                event_type,
                message,
                payload_json,
                started_at,
                ended_at,
                created_at
            FROM trace_index
            WHERE run_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (run_id,),
        )
        return self._rows_to_events(rows)

    def query_timeline_by_root(self, root_run_id: str) -> list[TraceEvent]:
        """按 root_run_id 查询整棵运行树的时间线，用于追踪 PlanExecutor 的完整执行流。"""
        rows = self.db.fetchall(
            """
            SELECT
                id,
                run_id,
                session_id,
                root_run_id,
                parent_run_id,
                parent_event_id,
                actor,
                action,
                status,
                input_summary,
                output_summary,
                event_type,
                message,
                payload_json,
                started_at,
                ended_at,
                created_at
            FROM trace_index
            WHERE root_run_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (root_run_id,),
        )
        return self._rows_to_events(rows)

    def query_timeline_by_session(self, session_id: str) -> list[TraceEvent]:
        """按 session_id 查询会话时间线。"""
        rows = self.db.fetchall(
            """
            SELECT
                id,
                run_id,
                session_id,
                root_run_id,
                parent_run_id,
                parent_event_id,
                actor,
                action,
                status,
                input_summary,
                output_summary,
                event_type,
                message,
                payload_json,
                started_at,
                ended_at,
                created_at
            FROM trace_index
            WHERE session_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (session_id,),
        )
        return self._rows_to_events(rows)

    @classmethod
    def reconcile_from_jsonl(
        cls,
        db: SQLiteDB,
        run_id: str,
        jsonl_path: Path,
    ) -> int:
        """从 JSONL 文件中恢复 SQLite 中缺失的 trace 事件。

        当 SQLite 写入失败但 JSONL 仍有数据时，可调用此方法将 JSONL 中的事件回写到 SQLite。

        Returns:
            成功恢复的事件数量。
        """
        if not jsonl_path.exists():
            return 0

        repo = cls(db)
        recovered = 0
        try:
            with jsonl_path.open("r", encoding="utf-8") as file:
                for line in file:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw = json.loads(line)
                        event = TraceEvent.model_validate(raw)
                    except Exception:
                        continue
                    # 检查 SQLite 中是否已存在此事件，避免重复写入
                    existing = db.fetchone(
                        "SELECT id FROM trace_index WHERE id = ?",
                        (event.id,),
                    )
                    if existing is None:
                        if repo.save_event(run_id, event):
                            recovered += 1
        except OSError:
            logger.warning("Failed to read JSONL for reconciliation: file=%s", jsonl_path)
        if recovered > 0:
            logger.info("Reconciled trace events from JSONL: run_id=%s recovered=%s", run_id, recovered)
        return recovered

    def _ensure_run_exists(self, *, run_id: str, session_id: str | None) -> None:
        """在仅有 trace 先写入时，补一个最小 run/session 记录。"""
        if not run_id:
            return
        effective_session_id = session_id or f"trace:{run_id}"
        timestamp = self.db.now()
        self.db.execute(
            """
            INSERT INTO sessions (id, created_at, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (effective_session_id, timestamp, timestamp),
        )
        self.db.execute(
            """
            INSERT INTO runs (
                run_id, session_id, model, task, status, step_count, final_output, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 0, '', ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                session_id = excluded.session_id,
                updated_at = excluded.updated_at
            """,
            (
                run_id,
                effective_session_id,
                "<trace-only>",
                "<trace-only>",
                "running",
                timestamp,
                timestamp,
            ),
        )

    def _rows_to_events(self, rows: list) -> list[TraceEvent]:
        """将数据库行转换为 TraceEvent 列表。"""
        events: list[TraceEvent] = []
        for row in rows:
            payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
            events.append(
                TraceEvent.model_validate(
                    {
                        "id": row["id"],
                        "run_id": row["run_id"],
                        "session_id": row["session_id"],
                        "root_run_id": row["root_run_id"],
                        "parent_run_id": row["parent_run_id"],
                        "parent_event_id": row["parent_event_id"],
                        "actor": row["actor"],
                        "action": row["action"],
                        "status": row["status"],
                        "input_summary": row["input_summary"],
                        "output_summary": row["output_summary"],
                        "event_type": row["event_type"],
                        "message": row["message"],
                        "started_at": row["started_at"],
                        "ended_at": row["ended_at"],
                        "created_at": row["created_at"],
                        "payload": payload,
                    }
                )
            )
        return events
