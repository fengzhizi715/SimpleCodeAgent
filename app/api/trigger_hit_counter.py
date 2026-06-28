"""Trigger hit counter for V3."""

from __future__ import annotations

from threading import Lock

from app.db.sqlite import SQLiteDB


class TriggerHitCounter:
    """Persist trigger rule hit counts to SQLite.

    Each record tracks how many times a rule was executed or skipped
    within a specific run.
    """

    def __init__(self, db: SQLiteDB | None = None) -> None:
        self._db = db or SQLiteDB()
        self._lock = Lock()

    def increment(self, run_id: str, rule_id: str, status: str) -> None:
        """Increment the hit count for a rule in a run."""
        if status not in ("executed", "skipped"):
            return
        with self._lock:
            if status == "executed":
                self._db.execute(
                    """
                    INSERT INTO trigger_hit_counts (run_id, rule_id, executed_count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(run_id, rule_id) DO UPDATE SET executed_count = executed_count + 1
                    """,
                    (run_id, rule_id),
                )
            else:
                self._db.execute(
                    """
                    INSERT INTO trigger_hit_counts (run_id, rule_id, skipped_count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(run_id, rule_id) DO UPDATE SET skipped_count = skipped_count + 1
                    """,
                    (run_id, rule_id),
                )

    def get_by_run(self, run_id: str) -> list[dict[str, object]]:
        """Return hit counts for all rules in a run."""
        rows = self._db.fetchall(
            "SELECT rule_id, executed_count, skipped_count FROM trigger_hit_counts WHERE run_id = ?",
            (run_id,),
        )
        return [dict(row) for row in rows]

    def get_by_rule(self, rule_id: str) -> list[dict[str, object]]:
        """Return hit counts for a rule across all runs."""
        rows = self._db.fetchall(
            "SELECT run_id, executed_count, skipped_count FROM trigger_hit_counts WHERE rule_id = ? ORDER BY run_id DESC",
            (rule_id,),
        )
        return [dict(row) for row in rows]

    def get_total(self, rule_id: str) -> dict[str, int]:
        """Return total executed/skipped counts for a rule across all runs."""
        row = self._db.fetchone(
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
                self._db.execute("DELETE FROM trigger_hit_counts WHERE run_id = ? AND rule_id = ?", (run_id, rule_id))
            elif run_id is not None:
                self._db.execute("DELETE FROM trigger_hit_counts WHERE run_id = ?", (run_id,))
            elif rule_id is not None:
                self._db.execute("DELETE FROM trigger_hit_counts WHERE rule_id = ?", (rule_id,))
            else:
                self._db.execute("DELETE FROM trigger_hit_counts")
