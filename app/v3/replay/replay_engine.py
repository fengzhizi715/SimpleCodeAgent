"""Simple replay entry for V3 event chains."""

from __future__ import annotations

from uuid import uuid4

from app.trace.repository import SQLiteTraceRepository
from app.v3 import build_default_skill_registry
from app.v3.contracts.event_contracts import EventType, V3Event
from app.v3.contracts.replay_contracts import ReplayMetadata, ReplayResult
from app.v3.contracts.skill_contracts import SkillInput
from app.v3.events.event_bus import EventBus
from app.v3.events.event_store import EventStore
from app.v3.runtime.skill_executor import SkillExecutor
from app.v3.skills.registry import SkillRegistry
from app.v3.trace import attach_trace_collector


async def replay_event_chain(
    *,
    repository: SQLiteTraceRepository,
    run_id: str,
    event_id: str,
    workspace_root: str | None = None,
    registry: SkillRegistry | None = None,
) -> ReplayResult:
    """Replay the first trigger-driven skill rooted at one source event."""
    events = _load_v3_events(repository=repository, run_id=run_id)
    source_event = next((event for event in events if event.event_id == event_id), None)
    if source_event is None:
        raise ValueError(f"未找到 event_id={event_id} 的 v3 event。")

    replay_target = _resolve_replay_target(source_event=source_event, events=events)
    replay_run_id = str(uuid4())
    event_bus = EventBus()
    event_store = EventStore()
    trace_events = attach_trace_collector(event_bus)
    skill_registry = registry or build_default_skill_registry(workspace_root=workspace_root)
    skill_executor = SkillExecutor(skill_registry)

    metadata = ReplayMetadata(
        replay_run_id=replay_run_id,
        source_run_id=run_id,
        source_event_id=source_event.event_id,
        execution_chain_id=source_event.execution_chain_id or source_event.event_id,
        target_skill_name=replay_target["target_skill_name"],
    )

    await _publish_replay_event(
        event_bus=event_bus,
        event_store=event_store,
        event=V3Event(
            run_id=replay_run_id,
            event_type=EventType.SKILL_STARTED.value,
            source=replay_target["target_skill_name"],
            parent_event_id=source_event.event_id,
            trigger_rule_id=replay_target["trigger_rule_id"],
            execution_chain_id=metadata.execution_chain_id,
            trigger_depth=0,
            payload={
                "replay": metadata.model_dump(mode="json"),
                "source_run_id": run_id,
                "source_event_id": source_event.event_id,
                "input_payload": replay_target["input_payload"],
            },
        ),
    )

    output = await skill_executor.execute(
        replay_target["target_skill_name"],
        SkillInput(
            run_id=replay_run_id,
            payload=replay_target["input_payload"],
            context={
                "workspace_root": workspace_root or replay_target["workspace_root"] or ".",
                "source_event": source_event.model_dump(mode="json"),
                "replay": metadata.model_dump(mode="json"),
            },
        ),
    )

    await _publish_replay_event(
        event_bus=event_bus,
        event_store=event_store,
        event=V3Event(
            run_id=replay_run_id,
            event_type=EventType.SKILL_FINISHED.value if output.success else EventType.SKILL_FAILED.value,
            source=replay_target["target_skill_name"],
            parent_event_id=source_event.event_id,
            trigger_rule_id=replay_target["trigger_rule_id"],
            execution_chain_id=metadata.execution_chain_id,
            trigger_depth=1,
            payload={
                "replay": metadata.model_dump(mode="json"),
                "source_run_id": run_id,
                "source_event_id": source_event.event_id,
                "summary": output.summary,
                "error": output.error,
                "data": output.data,
            },
        ),
    )

    return ReplayResult(
        metadata=metadata,
        success=output.success,
        summary=output.summary,
        error=output.error,
        output=output.data,
        events=[event.model_dump(mode="json") for event in event_store.list()],
        trace=[event.model_dump(mode="json") for event in trace_events],
    )


def _load_v3_events(*, repository: SQLiteTraceRepository, run_id: str) -> list[V3Event]:
    trace_events = repository.query_timeline(run_id)
    events: list[V3Event] = []
    for trace_event in trace_events:
        payload = trace_event.payload
        if not isinstance(payload, dict):
            continue
        try:
            events.append(V3Event.model_validate(payload))
        except Exception:
            continue
    if not events:
        raise ValueError(f"未找到 run_id={run_id} 的 v3 events。")
    return events


def _resolve_replay_target(*, source_event: V3Event, events: list[V3Event]) -> dict[str, object]:
    children = [
        event for event in events
        if event.parent_event_id == source_event.event_id and event.event_type == EventType.SKILL_STARTED.value
    ]
    children.sort(key=lambda item: (item.created_at, item.event_id))
    if not children:
        raise ValueError(f"event_id={source_event.event_id} 没有关联的 trigger skill 可重放。")
    target = children[0]
    input_payload = {}
    if isinstance(target.payload, dict):
        raw_input = target.payload.get("input_payload")
        if isinstance(raw_input, dict):
            input_payload = dict(raw_input)
    return {
        "target_skill_name": target.source,
        "trigger_rule_id": target.trigger_rule_id or target.payload.get("trigger_rule_id"),
        "input_payload": input_payload,
        "workspace_root": input_payload.get("workspace_root"),
    }


async def _publish_replay_event(*, event_bus: EventBus, event_store: EventStore, event: V3Event) -> None:
    event_store.append(event)
    await event_bus.publish(event)
