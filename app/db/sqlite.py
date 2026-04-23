"""SQLite 连接与基础仓储能力。"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import BASE_DIR
from app.db.migrations import SCHEMA_STATEMENTS


class SQLiteDB:
    """带自动建表能力的 SQLite 封装。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else BASE_DIR / ".simple_code_agent.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._write_lock = threading.RLock()
        self.initialize()

    def initialize(self) -> None:
        """在首次启动时创建数据表。"""
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            for statement in SCHEMA_STATEMENTS:
                conn.execute(statement)
            self._ensure_trace_index_columns(conn)
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_trace_index_session_id_created_at
                ON trace_index(session_id, created_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_trace_index_root_run_id_created_at
                ON trace_index(root_run_id, created_at)
                """
            )

    def _ensure_trace_index_columns(self, conn: sqlite3.Connection) -> None:
        """为已有数据库补齐 trace_index 的结构化列。"""
        existing_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(trace_index)").fetchall()
        }
        required_columns = {
            "session_id": "TEXT",
            "root_run_id": "TEXT",
            "parent_run_id": "TEXT",
            "parent_event_id": "TEXT",
            "actor": "TEXT",
            "action": "TEXT",
            "status": "TEXT",
            "input_summary": "TEXT",
            "output_summary": "TEXT",
            "started_at": "TEXT",
            "ended_at": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name in existing_columns:
                continue
            conn.execute(
                f"ALTER TABLE trace_index ADD COLUMN {column_name} {column_type}"
            )

    def connect(self) -> sqlite3.Connection:
        """打开或复用当前线程的 SQLite 连接。"""
        conn = getattr(self._local, "connection", None)
        if conn is not None:
            return conn
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000;")
        conn.execute("PRAGMA foreign_keys = ON;")
        self._local.connection = conn
        return conn

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        """执行单条写入语句。"""
        with self._write_lock:
            with self.connect() as conn:
                conn.execute(sql, params)

    def executemany(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        """批量执行写入语句。"""
        if not rows:
            return
        with self._write_lock:
            with self.connect() as conn:
                conn.executemany(sql, rows)

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        """执行查询并返回全部结果。"""
        with self.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        """执行查询并返回单条结果。"""
        with self.connect() as conn:
            return conn.execute(sql, params).fetchone()

    @staticmethod
    def now() -> str:
        """返回 UTC 时间戳字符串。"""
        return datetime.now(UTC).isoformat()
