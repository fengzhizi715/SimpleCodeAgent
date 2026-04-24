"""SQLite 连接与基础仓储能力。"""

from __future__ import annotations

import os
import shutil
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core import config
from app.core.config import get_sqlite_database_path
from app.core.logger import get_logger
from app.db.migrations import SCHEMA_STATEMENTS

logger = get_logger(__name__)


def _maybe_migrate_legacy_data_app_db(target: Path, *, legacy_path: Path) -> None:
    """若曾使用根目录 data/app.db，在首次未指定自定义路径时迁移为统一库。"""
    if (os.getenv("SQLITE_DB_PATH") or "").strip():
        return
    if not legacy_path.exists():
        return
    if target.exists() and legacy_path.resolve() != target.resolve():
        logger.warning(
            "旧库 %s 仍存在，且统一库 %s 已存在。请自行核对后删除其中一份。",
            legacy_path,
            target,
        )
        return
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    logger.info("将旧库迁移为统一主库：%s -> %s", legacy_path, target)
    shutil.move(str(legacy_path), str(target))


class SQLiteDB:
    """带自动建表能力的 SQLite 封装。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is not None:
            self.db_path = Path(db_path)
        else:
            default_target = get_sqlite_database_path()
            _maybe_migrate_legacy_data_app_db(
                default_target, legacy_path=config.BASE_DIR / "data" / "app.db"
            )
            self.db_path = default_target
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
            self._ensure_runs_agent_version_column(conn)
            self._ensure_runs_hierarchy_columns(conn)
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

    def _ensure_runs_agent_version_column(self, conn: sqlite3.Connection) -> None:
        """为 runs 表补齐 agent_version，并回填含 workspace 的 V2 记录。"""
        existing_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(runs)").fetchall()
        }
        if "agent_version" not in existing_columns:
            conn.execute("ALTER TABLE runs ADD COLUMN agent_version TEXT")
        conn.execute(
            """
            UPDATE runs
            SET agent_version = 'v2'
            WHERE run_id IN (SELECT run_id FROM v2_workspaces)
              AND (agent_version IS NULL OR agent_version = '')
            """
        )

    def _ensure_runs_hierarchy_columns(self, conn: sqlite3.Connection) -> None:
        """为 runs 表补齐层级字段，并尽力回填旧数据。"""
        existing_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(runs)").fetchall()
        }
        if "is_top_level" not in existing_columns:
            conn.execute("ALTER TABLE runs ADD COLUMN is_top_level INTEGER NOT NULL DEFAULT 1")
        if "parent_run_id" not in existing_columns:
            conn.execute("ALTER TABLE runs ADD COLUMN parent_run_id TEXT")
        conn.execute(
            """
            UPDATE runs
            SET parent_run_id = (
                    SELECT ti.root_run_id
                    FROM trace_index ti
                    WHERE ti.run_id = runs.run_id
                      AND ti.root_run_id IS NOT NULL
                      AND ti.root_run_id != runs.run_id
                    ORDER BY ti.created_at DESC
                    LIMIT 1
                ),
                is_top_level = 0
            WHERE EXISTS (
                SELECT 1
                FROM trace_index ti
                WHERE ti.run_id = runs.run_id
                  AND ti.root_run_id IS NOT NULL
                  AND ti.root_run_id != runs.run_id
            )
            """
        )
        # trace 缺失时的兜底回填：旧版本曾使用 task 文案标记 planner/direct-tool 子运行。
        conn.execute(
            """
            UPDATE runs
            SET is_top_level = 0
            WHERE task LIKE '[direct-tool] %'
               OR (task LIKE '总任务：%' AND task LIKE '%当前是第 %/% 步%')
            """
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
