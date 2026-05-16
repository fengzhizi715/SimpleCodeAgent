"""Trigger hit counter for V3."""

from __future__ import annotations

from threading import Lock

from app.db.sqlite import SQLiteDB


class TriggerHitCounter:
    """Persist trigger rule hit counts to SQLite.

    Each record tracks how many times a rule was executed or skipped
    within a specific run.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._init_table()

    def _init_table(self) -> None:
        SQLiteDB().execute(
            """
            CREATE TABLE IF NOT EXISTS trigger_hit_counts (
                run_id TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                executed_count INTEGER DEFAULT 0,
                skipped_count INTEGER DEFAULT 0,
                PRIMARY KEY (run_id, rule_id)
            )
            """
        )

    def increment(self, run_id: str, rule_id: str, status: str) -> None:
        """Increment the hit count for a rule in a run."""
        if status not in ("executed", "skipped"):
            return
        with self._lock:
            if status == "executed":
                SQLiteDB().execute(
                    """
                    INSERT INTO trigger_hit_counts (run_id, rule_id, executed_count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(run_id, rule_id) DO UPDATE SET executed_count = executed_count + 1
                    """,
                    (run_id, rule_id),
                )
            else:
                SQLiteDB().execute(
                    """
                    INSERT INTO trigger_hit_counts (run_id, rule_id, skipped_count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(run_id, rule_id) DO UPDATE SET skipped_count = skipped_count + 1
                    """,
                    (run_id, rule_id),
                )

    def get_by_run(self, run_id: str) -> list[dict[str, object]]:
        """Return hit counts for all rules in a run."""
        rows = SQLiteDB().fetchall(
            "SELECT rule_id, executed_count, skipped_count FROM trigger_hit_counts WHERE run_id = ?",
            (run_id,),
        )
        return [dict(row) for row in rows]

    def get_by_rule(self, rule_id: str) -> list[dict[str, object]]:
        """Return hit counts for a rule across all runs."""
        rows = SQLiteDB().fetchall(
            "SELECT run_id, executed_count, skipped_count FROM trigger_hit_counts WHERE rule_id = ? ORDER BY run_id DESC",
            (rule_id,),
        )
        return [dict(row) for row in rows]

    def get_total(self, rule_id: str) -> dict[str, int]:
        """Return total executed/skipped counts for a rule across all runs."""
        row = SQLiteDB().fetchone(
            "SELECT SUM(executed_count) as total_executed, SUM(skipped_count) as total_skipped FROM trigger_hit_counts WHERE rule_id = ?",
            (rule_id,),
        )
        if row is None:
            return {"executed": 0, "skipped": 0}
        return {
            "executed": int(row["total_executed"] or 0),
            "skipped": int(row["total_skipped"] or 0),
        }

    def reset(self, run_id: str | None = None, rule_id: str | None = None) -> None:
        """Reset hit counts. If both None, reset all."""
        with self._lock:
            if run_id is not None and rule_id is not None:
                SQLiteDB().execute("DELETE FROM trigger_hit_counts WHERE run_id = ? AND rule_id = ?", (run_id, rule_id))
            elif run_id is not None:
                SQLiteDB().execute("DELETE FROM trigger_hit_counts WHERE run_id = ?", (run_id,))
            elif rule_id is not None:
                SQLiteDB().execute("DELETE FROM trigger_hit_counts WHERE rule_id = ?", (rule_id,))
            else:
                SQLiteDB().execute("DELETE FROM trigger_hit_counts")
