"""SQLite 表结构迁移定义。"""

from __future__ import annotations

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT,
        name TEXT,
        tool_call_id TEXT,
        tool_calls_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        FOREIGN KEY(session_id) REFERENCES sessions(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        model TEXT NOT NULL,
        task TEXT NOT NULL,
        status TEXT,
        step_count INTEGER NOT NULL DEFAULT 0,
        final_output TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(session_id) REFERENCES sessions(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trace_index (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        message TEXT NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES runs(run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS summaries (
        session_id TEXT PRIMARY KEY,
        summary TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(session_id) REFERENCES sessions(id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_messages_session_id_id
    ON messages(session_id, id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_runs_session_id_created_at
    ON runs(session_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_trace_index_run_id_created_at
    ON trace_index(run_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_sessions_updated_at
    ON sessions(updated_at)
    """,
]
