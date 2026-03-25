"""SQLite 连接与基础仓储能力。"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import BASE_DIR
from app.db.migrations import SCHEMA_STATEMENTS


class SQLiteDB:
    """带自动建表能力的 SQLite 封装。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else BASE_DIR / ".agent_data.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def initialize(self) -> None:
        """在首次启动时创建数据表。"""
        with self.connect() as conn:
            for statement in SCHEMA_STATEMENTS:
                conn.execute(statement)

    def connect(self) -> sqlite3.Connection:
        """打开一个支持按列名访问结果的连接。"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        """执行单条写入语句。"""
        with self.connect() as conn:
            conn.execute(sql, params)

    def executemany(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        """批量执行写入语句。"""
        if not rows:
            return
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
