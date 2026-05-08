"""Trace helpers for V3."""

from __future__ import annotations

from app.v3.events.event_bus import EventBus
from app.contracts.trace import TraceEvent
from app.v3.contracts.event_contracts import V3Event


def event_to_trace(event: V3Event) -> TraceEvent:
    """Convert one V3 event into a shared TraceEvent."""
    return TraceEvent(
        run_id=event.run_id,
        actor=event.source,
        event_type=event.event_type,
        message=f"v3:{event.event_type}",
        payload=event.model_dump(mode="json"),
    )


def attach_trace_collector(event_bus: EventBus) -> list[TraceEvent]:
    """Attach a tiny in-memory trace collector to an event bus."""
    traces: list[TraceEvent] = []

    async def _handler(event: V3Event) -> None:
        traces.append(event_to_trace(event))

    for event_type in [
        "graph_started",
        "graph_finished",
        "skill_started",
        "skill_finished",
        "skill_failed",
        "trigger_skipped",
        "test_failed",
        "code_updated",
    ]:
        event_bus.subscribe(event_type, _handler)
    return traces
