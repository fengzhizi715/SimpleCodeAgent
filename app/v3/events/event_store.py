"""In-memory event storage for V3 with V3.2 persistence enhancements."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.v3.contracts.event_contracts import V3Event
from app.v3.events.event_history import EventChainTrace, build_event_chain_trace

FlushCallback = Callable[[list[V3Event]], Awaitable[None] | None]


class EventStore:
    """Store V3 events in memory with optional persistence.

    Events are accumulated in memory and can be flushed to a persistent
    backend via the ``flush_callback``.  Callers should call ``flush()``
    explicitly at appropriate checkpoints (e.g. after graph execution).

    V3.2 enhancements add query methods for:
    - by event_type
    - by source
    - by time range
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

    def get(self, event_id: str) -> V3Event | None:
        """Return one event by id."""
        for event in self._events:
            if event.event_id == event_id:
                return event
        return None

    def list_by_parent_event_id(self, parent_event_id: str) -> list[V3Event]:
        """Return direct child events for a parent event id."""
        return [event for event in self._events if event.parent_event_id == parent_event_id]

    def list_by_execution_chain_id(self, execution_chain_id: str) -> list[V3Event]:
        """Return events associated with one execution chain."""
        return [event for event in self._events if event.execution_chain_id == execution_chain_id]

    def list_by_event_type(self, event_type: str) -> list[V3Event]:
        """Return events matching a specific event type."""
        return [event for event in self._events if event.event_type == event_type]

    def list_by_event_type_and_run(self, event_type: str, run_id: str) -> list[V3Event]:
        """Return events matching a specific event type within a run."""
        return [
            event
            for event in self._events
            if event.event_type == event_type and event.run_id == run_id
        ]

    def list_by_source(self, source: str) -> list[V3Event]:
        """Return events emitted by a specific source."""
        return [event for event in self._events if event.source == source]

    def list_by_source_and_run(self, source: str, run_id: str) -> list[V3Event]:
        """Return events from a specific source within a run."""
        return [
            event
            for event in self._events
            if event.source == source and event.run_id == run_id
        ]

    def list_by_time_range(
        self,
        run_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[V3Event]:
        """Return events within a time range for a given run.

        Args:
            run_id: The run to filter by.
            start: ISO format datetime string for start bound (inclusive).
            end: ISO format datetime string for end bound (inclusive).
        """
        events = self.list_by_run_id(run_id)
        if start is not None:
            events = [e for e in events if e.created_at.isoformat() >= start]
        if end is not None:
            events = [e for e in events if e.created_at.isoformat() <= end]
        return events

    def list_by_trigger_depth(self, run_id: str, depth: int) -> list[V3Event]:
        """Return events at a specific trigger depth within a run."""
        return [
            event
            for event in self._events
            if event.run_id == run_id and event.trigger_depth == depth
        ]

    def list_by_correlation_id(self, correlation_id: str) -> list[V3Event]:
        """Return events sharing a correlation id."""
        return [
            event
            for event in self._events
            if event.correlation_id == correlation_id
        ]

    def get_chain_trace(self, execution_chain_id: str) -> EventChainTrace | None:
        """Return a structured trace for one execution chain."""
        return build_event_chain_trace(self._events, execution_chain_id=execution_chain_id)

    def get_chain_trace_for_event(self, event_id: str) -> EventChainTrace | None:
        """Resolve an event to its execution chain and return that chain trace."""
        event = self.get(event_id)
        if event is None:
            return None
        chain_id = event.execution_chain_id or event.event_id
        return build_event_chain_trace(self._events, execution_chain_id=chain_id, root_event_id=event_id)

    def count_by_run_id(self, run_id: str) -> int:
        """Return the number of events for a run."""
        return len(self.list_by_run_id(run_id))

    def count_by_event_type(self, run_id: str) -> dict[str, int]:
        """Return event counts by type for a run."""
        events = self.list_by_run_id(run_id)
        counts: dict[str, int] = {}
        for event in events:
            counts[event.event_type] = counts.get(event.event_type, 0) + 1
        return counts

    async def flush(self) -> None:
        """Flush pending events to the persistence callback."""
        if not self._pending_events or self._flush_callback is None:
            return
        pending = list(self._pending_events)
        result = self._flush_callback(pending)
        if isinstance(result, Awaitable):
            await result
        self._pending_events.clear()
