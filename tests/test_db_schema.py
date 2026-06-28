"""SQLite schema and API persistence boundary tests."""

from __future__ import annotations

from pathlib import Path

from app.api.trigger_state_store import TriggerRuleStateStore
from app.db.sqlite import SQLiteDB


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
