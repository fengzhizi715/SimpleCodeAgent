"""Trigger rule state store for V3."""

from __future__ import annotations

from threading import Lock


class TriggerRuleStateStore:
    """Track runtime enable/disable state for trigger rules.

    This store lives at the API layer and provides a persistent view of
    trigger rule states across runs.  It does NOT modify the per-run
    TriggerRegistry directly; instead, callers should consult this store
    when building execution kernels.
    """

    def __init__(self) -> None:
        self._enabled: dict[str, bool] = {}
        self._lock = Lock()

    def is_enabled(self, rule_id: str) -> bool:
        """Return whether a rule is enabled. Defaults to True."""
        with self._lock:
            return self._enabled.get(rule_id, True)

    def set_enabled(self, rule_id: str, enabled: bool) -> None:
        """Set the enabled state for a rule."""
        with self._lock:
            self._enabled[rule_id] = enabled

    def toggle(self, rule_id: str) -> bool:
        """Toggle the enabled state and return the new value."""
        with self._lock:
            current = self._enabled.get(rule_id, True)
            self._enabled[rule_id] = not current
            return self._enabled[rule_id]

    def get_all(self) -> dict[str, bool]:
        """Return a snapshot of all overridden states."""
        with self._lock:
            return dict(self._enabled)

    def reset(self, rule_id: str | None = None) -> None:
        """Reset state for one rule or all rules back to default (enabled)."""
        with self._lock:
            if rule_id is not None:
                self._enabled.pop(rule_id, None)
            else:
                self._enabled.clear()
