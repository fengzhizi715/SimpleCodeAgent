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
        workdir TEXT,
        is_top_level INTEGER NOT NULL DEFAULT 1,
        parent_run_id TEXT,
        status TEXT,
        step_count INTEGER NOT NULL DEFAULT 0,
        prompt_tokens INTEGER NOT NULL DEFAULT 0,
        completion_tokens INTEGER NOT NULL DEFAULT 0,
        total_tokens INTEGER NOT NULL DEFAULT 0,
        final_output TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        agent_version TEXT,
        FOREIGN KEY(session_id) REFERENCES sessions(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trace_index (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        session_id TEXT,
        root_run_id TEXT,
        parent_run_id TEXT,
        parent_event_id TEXT,
        actor TEXT,
        action TEXT,
        status TEXT,
        input_summary TEXT,
        output_summary TEXT,
        event_type TEXT NOT NULL,
        message TEXT NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        started_at TEXT,
        ended_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES runs(run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS v2_workspaces (
        run_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        user_goal TEXT NOT NULL,
        current_plan_json TEXT NOT NULL DEFAULT '{}',
        project_summary TEXT NOT NULL DEFAULT '',
        latest_patch_summary TEXT NOT NULL DEFAULT '',
        latest_test_result_json TEXT NOT NULL DEFAULT '{}',
        artifacts_index_json TEXT NOT NULL DEFAULT '[]',
        execution_notes_json TEXT NOT NULL DEFAULT '[]',
        private_context_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(session_id) REFERENCES sessions(id),
        FOREIGN KEY(run_id) REFERENCES runs(run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS v2_delegations (
        delegation_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        step_id TEXT,
        parent_agent_id TEXT NOT NULL,
        target_agent TEXT NOT NULL,
        task_id TEXT NOT NULL,
        status TEXT NOT NULL,
        summary TEXT NOT NULL DEFAULT '',
        error_message TEXT,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        FOREIGN KEY(run_id) REFERENCES runs(run_id),
        FOREIGN KEY(session_id) REFERENCES sessions(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS v2_artifacts (
        artifact_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        key TEXT NOT NULL,
        type TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        producer_agent TEXT,
        summary TEXT NOT NULL,
        content_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES runs(run_id),
        FOREIGN KEY(session_id) REFERENCES sessions(id)
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
    CREATE INDEX IF NOT EXISTS idx_v2_workspaces_session_id_updated_at
    ON v2_workspaces(session_id, updated_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_v2_delegations_run_id_started_at
    ON v2_delegations(run_id, started_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_v2_delegations_session_id_started_at
    ON v2_delegations(session_id, started_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_v2_artifacts_run_id_created_at
    ON v2_artifacts(run_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_v2_artifacts_session_id_key_version
    ON v2_artifacts(session_id, key, version)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_sessions_updated_at
    ON sessions(updated_at)
    """,
]
