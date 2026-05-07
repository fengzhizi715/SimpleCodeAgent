"""Trace helpers for V3."""

from __future__ import annotations

from app.contracts.trace import TraceEvent
from app.v3.contracts.event_contracts import V3Event


class V3TraceCollector:
    """Convert V3 events into shared trace events."""

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    def record(self, event: V3Event) -> None:
        """Record one V3 event as a shared TraceEvent."""
        self._events.append(
            TraceEvent(
                run_id=event.run_id,
                actor=event.source,
                event_type=event.event_type,
                message=f"v3:{event.event_type}",
                payload=event.model_dump(mode="json"),
            )
        )

    def list(self) -> list[TraceEvent]:
        """List collected trace events."""
        return list(self._events)
