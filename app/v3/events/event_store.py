"""In-memory event storage for V3."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.v3.contracts.event_contracts import V3Event

FlushCallback = Callable[[list[V3Event]], Awaitable[None] | None]


class EventStore:
    """Store V3 events in memory with optional persistence.

    Events are accumulated in memory and can be flushed to a persistent
    backend via the ``flush_callback``.  Callers should call ``flush()``
    explicitly at appropriate checkpoints (e.g. after graph execution).
    """

    def __init__(
        self,
        *,
        flush_callback: FlushCallback | None = None,
    ) -> None:
        self._events: list[V3Event] = []
        self._flush_callback = flush_callback
        self._pending_events: list[V3Event] = []

    def append(self, event: V3Event) -> None:
        """Append a new event."""
        self._events.append(event)
        self._pending_events.append(event)

    def list(self) -> list[V3Event]:
        """Return all events in insertion order."""
        return list(self._events)

    def list_by_run_id(self, run_id: str) -> list[V3Event]:
        """Return all events for a run."""
        return [event for event in self._events if event.run_id == run_id]

    async def flush(self) -> None:
        """Flush pending events to the persistence callback."""
        if not self._pending_events or self._flush_callback is None:
            return
        pending = list(self._pending_events)
        result = self._flush_callback(pending)
        if isinstance(result, Awaitable):
            await result
        self._pending_events.clear()
