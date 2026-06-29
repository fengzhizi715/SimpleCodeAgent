"""SQLite schema and API persistence boundary tests."""

from __future__ import annotations

from pathlib import Path

from app.api.trigger_state_store import TriggerRuleStateStore
from app.db.sqlite import SQLiteDB
from app.v1.memory.repository import SQLiteMemoryRepository


def test_sqlite_schema_includes_v3_trigger_tables(tmp_path: Path) -> None:
    db = SQLiteDB(tmp_path / "schema.sqlite3")

    rows = db.fetchall(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name IN ('trigger_hit_counts', 'trigger_rule_states')
        ORDER BY name
        """
    )

    assert [row["name"] for row in rows] == [
        "trigger_hit_counts",
        "trigger_rule_states",
    ]


def test_trigger_rule_state_store_persists_overrides(tmp_path: Path) -> None:
    db = SQLiteDB(tmp_path / "trigger-state.sqlite3")
    store = TriggerRuleStateStore(db)

    store.set_enabled("rule-a", False)

    reloaded = TriggerRuleStateStore(db)
    assert reloaded.is_enabled("rule-a") is False
    assert reloaded.get_all() == {"rule-a": False}

    reloaded.reset("rule-a")
    assert TriggerRuleStateStore(db).is_enabled("rule-a") is True


def test_cleanup_old_sessions_removes_v2_child_rows_before_runs(tmp_path: Path) -> None:
    repo = SQLiteMemoryRepository(tmp_path / "cleanup.sqlite3")
    db = repo.db
    old_timestamp = "2000-01-01T00:00:00+00:00"

    db.execute(
        """
        INSERT INTO sessions (id, created_at, updated_at)
        VALUES (?, ?, ?)
        """,
        ("old-session", old_timestamp, old_timestamp),
    )
    db.execute(
        """
        INSERT INTO runs (
            run_id, session_id, model, task, status, step_count, final_output,
            created_at, updated_at, agent_version
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "old-run",
            "old-session",
            "model",
            "task",
            "completed",
            1,
            "done",
            old_timestamp,
            old_timestamp,
            "v2",
        ),
    )
    db.execute(
        """
        INSERT INTO v2_workspaces (
            run_id, session_id, user_goal, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        ("old-run", "old-session", "goal", old_timestamp, old_timestamp),
    )
    db.execute(
        """
        INSERT INTO v2_delegations (
            delegation_id, run_id, session_id, parent_agent_id, target_agent,
            task_id, status, started_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "delegation-old",
            "old-run",
            "old-session",
            "orchestrator",
            "coder",
            "task-old",
            "completed",
            old_timestamp,
        ),
    )
    db.execute(
        """
        INSERT INTO v2_artifacts (
            artifact_id, run_id, session_id, key, type, summary, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "artifact-old",
            "old-run",
            "old-session",
            "patch",
            "diff",
            "summary",
            old_timestamp,
        ),
    )

    cleaned = repo.cleanup_old_sessions(max_age_days=30)

    assert cleaned == 1
    assert db.fetchone("SELECT id FROM sessions WHERE id = ?", ("old-session",)) is None
    assert db.fetchone("SELECT run_id FROM runs WHERE run_id = ?", ("old-run",)) is None
    assert db.fetchall("SELECT run_id FROM v2_workspaces WHERE run_id = ?", ("old-run",)) == []
    assert db.fetchall("SELECT run_id FROM v2_delegations WHERE run_id = ?", ("old-run",)) == []
    assert db.fetchall("SELECT run_id FROM v2_artifacts WHERE run_id = ?", ("old-run",)) == []


def test_sqlite_memory_repository_does_not_cleanup_on_init_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "no-auto-cleanup.sqlite3"
    db = SQLiteDB(db_path)
    old_timestamp = "2000-01-01T00:00:00+00:00"
    monkeypatch.delenv("SQLITE_AUTO_CLEANUP_MAX_AGE_DAYS", raising=False)
    SQLiteMemoryRepository._cleanup_ran = False
    db.execute(
        """
        INSERT INTO sessions (id, created_at, updated_at)
        VALUES (?, ?, ?)
        """,
        ("old-session", old_timestamp, old_timestamp),
    )

    SQLiteMemoryRepository(db_path)

    assert db.fetchone("SELECT id FROM sessions WHERE id = ?", ("old-session",)) is not None
