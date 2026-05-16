"""Cooldown state for V3 trigger governance."""

from __future__ import annotations

import time


class CooldownManager:
    """Track per-run cooldown windows for trigger rules."""

    def __init__(self) -> None:
        self._windows: dict[tuple[str, str], float] = {}

    def is_in_cooldown(self, *, run_id: str, cooldown_key: str, cooldown_seconds: float | None) -> bool:
        """Return True when the cooldown window is still active."""
        if cooldown_seconds is None or cooldown_seconds <= 0:
            return False
        last_fired_at = self._windows.get((run_id, cooldown_key))
        if last_fired_at is None:
            return False
        return (time.monotonic() - last_fired_at) < cooldown_seconds

    def mark(self, *, run_id: str, cooldown_key: str, cooldown_seconds: float | None) -> None:
        """Start or refresh one cooldown window."""
        if cooldown_seconds is None or cooldown_seconds <= 0:
            return
        self._windows[(run_id, cooldown_key)] = time.monotonic()
