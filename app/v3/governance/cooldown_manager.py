"""Cooldown state for V3 trigger and autonomy governance."""

from __future__ import annotations

import time


class CooldownManager:
    """Track per-run cooldown windows for trigger rules, skills, and autonomy policies."""

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

    def get_remaining_seconds(self, *, run_id: str, cooldown_key: str, cooldown_seconds: float | None) -> float:
        """Return remaining cooldown seconds, or 0.0 if not in cooldown."""
        if cooldown_seconds is None or cooldown_seconds <= 0:
            return 0.0
        last_fired_at = self._windows.get((run_id, cooldown_key))
        if last_fired_at is None:
            return 0.0
        elapsed = time.monotonic() - last_fired_at
        remaining = cooldown_seconds - elapsed
        return max(0.0, remaining)

    def clear(self, *, run_id: str | None = None, cooldown_key: str | None = None) -> None:
        """Clear cooldown windows. If both args are None, clear all."""
        if run_id is None and cooldown_key is None:
            self._windows.clear()
            return
        keys_to_remove = [
            k for k in self._windows
            if (run_id is None or k[0] == run_id)
            and (cooldown_key is None or k[1] == cooldown_key)
        ]
        for k in keys_to_remove:
            del self._windows[k]
