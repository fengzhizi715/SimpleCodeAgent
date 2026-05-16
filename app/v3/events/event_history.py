"""Readable event history helpers for V3."""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, ConfigDict, Field

from app.v3.contracts.event_contracts import V3Event


class EventChainItem(BaseModel):
    """One readable event entry inside a chain trace."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: str
    source: str
    parent_event_id: str | None = None
    trigger_rule_id: str | None = None
    execution_chain_id: str
    trigger_depth: int = 0
    node_id: str | None = None
    summary: str | None = None
    error: str | None = None
    created_at: str


class EventChainTrace(BaseModel):
    """A structured, queryable view of one V3 event chain."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    execution_chain_id: str
    root_event_id: str | None = None
    root_event_type: str | None = None
    items: list[EventChainItem] = Field(default_factory=list)


def build_event_chain_trace(
    events: list[V3Event],
    *,
    execution_chain_id: str,
    root_event_id: str | None = None,
) -> EventChainTrace | None:
    """Build one chain trace from V3 events."""
    chain_events = [
        event for event in sorted(events, key=lambda item: (item.created_at, item.event_id))
        if event.execution_chain_id == execution_chain_id
    ]
    if not chain_events:
        return None

    if root_event_id is not None:
        root_event = next((event for event in chain_events if event.event_id == root_event_id), None)
        if root_event is None:
            return None
        chain_events = _collect_descendants(chain_events, root_event_id=root_event_id)
    else:
        item_ids = {event.event_id for event in chain_events}
        root_event = next(
            (
                event
                for event in chain_events
                if event.parent_event_id is None or event.parent_event_id not in item_ids
            ),
            chain_events[0],
        )
    return EventChainTrace(
        run_id=chain_events[0].run_id,
        execution_chain_id=execution_chain_id,
        root_event_id=root_event.event_id,
        root_event_type=root_event.event_type,
        items=[_to_chain_item(event) for event in chain_events],
    )


def format_event_chain_trace(trace: EventChainTrace) -> str:
    """Render one event chain trace as readable text."""
    if not trace.items:
        return (
            f"Event Chain: {trace.execution_chain_id}\n"
            "  <empty>"
        )

    children_by_parent: dict[str | None, list[EventChainItem]] = defaultdict(list)
    items_by_id = {item.event_id: item for item in trace.items}
    for item in trace.items:
        parent_id = item.parent_event_id if item.parent_event_id in items_by_id else None
        children_by_parent[parent_id].append(item)
    for children in children_by_parent.values():
        children.sort(key=lambda item: (item.created_at, item.event_id))

    lines = [
        f"Event Chain: {trace.execution_chain_id}",
        f"Run: {trace.run_id}",
        f"Root: {trace.root_event_type or 'unknown'} ({trace.root_event_id or 'n/a'})",
    ]

    visited: set[str] = set()

    def _render(item: EventChainItem, depth: int) -> None:
        indent = "  " * depth
        details: list[str] = [f"{item.event_type}", f"source={item.source}"]
        if item.node_id:
            details.append(f"node_id={item.node_id}")
        if item.trigger_rule_id:
            details.append(f"rule_id={item.trigger_rule_id}")
        if item.summary:
            details.append(f"summary={item.summary}")
        if item.error:
            details.append(f"error={item.error}")
        lines.append(f"{indent}- " + " | ".join(details))
        visited.add(item.event_id)
        for child in children_by_parent.get(item.event_id, []):
            _render(child, depth + 1)

    roots = children_by_parent.get(None, [])
    for root in roots:
        _render(root, 1)

    # Defensive fallback for malformed chains so query results are still readable.
    for item in trace.items:
        if item.event_id not in visited:
            _render(item, 1)

    return "\n".join(lines)


def _to_chain_item(event: V3Event) -> EventChainItem:
    payload = event.payload if isinstance(event.payload, dict) else {}
    return EventChainItem(
        event_id=event.event_id,
        event_type=event.event_type,
        source=event.source,
        parent_event_id=event.parent_event_id,
        trigger_rule_id=event.trigger_rule_id or _coerce_str(payload.get("trigger_rule_id")),
        execution_chain_id=event.execution_chain_id or event.event_id,
        trigger_depth=event.trigger_depth,
        node_id=_coerce_str(payload.get("node_id")),
        summary=_coerce_str(payload.get("summary")),
        error=_coerce_str(payload.get("error")),
        created_at=event.created_at.isoformat(),
    )


def _collect_descendants(events: list[V3Event], *, root_event_id: str) -> list[V3Event]:
    children_by_parent: dict[str, list[V3Event]] = defaultdict(list)
    items_by_id = {event.event_id: event for event in events}
    for event in events:
        if event.parent_event_id is not None and event.parent_event_id in items_by_id:
            children_by_parent[event.parent_event_id].append(event)

    selected: list[V3Event] = []
    queue = [root_event_id]
    seen: set[str] = set()
    while queue:
        current_id = queue.pop(0)
        if current_id in seen:
            continue
        seen.add(current_id)
        current = items_by_id.get(current_id)
        if current is None:
            continue
        selected.append(current)
        for child in sorted(children_by_parent.get(current_id, []), key=lambda item: (item.created_at, item.event_id)):
            queue.append(child.event_id)
    return selected


def _coerce_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
