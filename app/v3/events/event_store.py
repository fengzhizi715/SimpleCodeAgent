"""In-memory event storage for V3."""

from __future__ import annotations

from app.v3.contracts.event_contracts import V3Event


class EventStore:
    """Store V3 events in memory for inspection."""

    def __init__(self) -> None:
        self._events: list[V3Event] = []

    def append(self, event: V3Event) -> None:
        """Append a new event."""
        self._events.append(event)

    def list(self) -> list[V3Event]:
        """Return all events in insertion order."""
        return list(self._events)

    def list_by_run_id(self, run_id: str) -> list[V3Event]:
        """Return all events for a run."""
        return [event for event in self._events if event.run_id == run_id]
