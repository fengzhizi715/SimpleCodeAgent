"""Trigger rule state store for V3."""

from __future__ import annotations

from threading import RLock

from app.db.sqlite import SQLiteDB


class TriggerRuleStateStore:
    """Track runtime enable/disable state for trigger rules.

    This store lives at the API layer and provides a persistent view of
    trigger rule states across runs.  It does NOT modify the per-run
    TriggerRegistry directly; instead, callers should consult this store
    when building execution kernels.
    """

    def __init__(self, db: SQLiteDB | None = None) -> None:
        self._db = db or SQLiteDB()
        self._lock = RLock()

    def is_enabled(self, rule_id: str) -> bool:
        """Return whether a rule is enabled. Defaults to True."""
        with self._lock:
            row = self._db.fetchone(
                "SELECT enabled FROM trigger_rule_states WHERE rule_id = ?",
                (rule_id,),
            )
            if row is None:
                return True
            return bool(row["enabled"])

    def set_enabled(self, rule_id: str, enabled: bool) -> None:
        """Set the enabled state for a rule."""
        with self._lock:
            timestamp = self._db.now()
            self._db.execute(
                """
                INSERT INTO trigger_rule_states (rule_id, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(rule_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (rule_id, 1 if enabled else 0, timestamp, timestamp),
            )

    def toggle(self, rule_id: str) -> bool:
        """Toggle the enabled state and return the new value."""
        with self._lock:
            current = self.is_enabled(rule_id)
            new_state = not current
            self.set_enabled(rule_id, new_state)
            return new_state

    def get_all(self) -> dict[str, bool]:
        """Return a snapshot of all overridden states."""
        with self._lock:
            rows = self._db.fetchall(
                "SELECT rule_id, enabled FROM trigger_rule_states ORDER BY rule_id ASC"
            )
            return {str(row["rule_id"]): bool(row["enabled"]) for row in rows}

    def reset(self, rule_id: str | None = None) -> None:
        """Reset state for one rule or all rules back to default (enabled)."""
        with self._lock:
            if rule_id is not None:
                self._db.execute(
                    "DELETE FROM trigger_rule_states WHERE rule_id = ?",
                    (rule_id,),
                )
            else:
                self._db.execute("DELETE FROM trigger_rule_states")
