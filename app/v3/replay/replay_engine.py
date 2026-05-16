"""Replay engine for V3 with V3.2 enhancements."""

from __future__ import annotations

from uuid import uuid4

from app.trace.repository import SQLiteTraceRepository
from app.v3 import build_default_skill_registry
from app.v3.contracts.event_contracts import EventType, V3Event
from app.v3.contracts.replay_contracts import (
    ReplayChainView,
    ReplayEntryType,
    ReplayMetadata,
    ReplayMode,
    ReplayPlan,
    ReplayResult,
)
from app.v3.contracts.skill_contracts import SkillInput
from app.v3.events.event_bus import EventBus
from app.v3.events.event_store import EventStore
from app.v3.trigger.trigger_engine import TriggerEngine
from app.v3.trigger.trigger_registry import TriggerRegistry
from app.v3.runtime.skill_executor import SkillExecutor
from app.v3.skills.registry import SkillRegistry
from app.v3.trace import attach_trace_collector
from app.v3.contracts.trigger_contracts import TriggerRule


async def replay_event_chain(
    *,
    repository: SQLiteTraceRepository,
    run_id: str,
    event_id: str,
    workspace_root: str | None = None,
    registry: SkillRegistry | None = None,
) -> ReplayResult:
    """Replay the first trigger-driven skill rooted at one source event.

    This is the original V3 replay, equivalent to first_action_replay mode.
    """
    return await replay_by_event(
        repository=repository,
        run_id=run_id,
        event_id=event_id,
        workspace_root=workspace_root,
        registry=registry,
    )


async def replay_by_run(
    *,
    repository: SQLiteTraceRepository,
    run_id: str,
    workspace_root: str | None = None,
    registry: SkillRegistry | None = None,
) -> ReplayPlan:
    """List available replay targets for an entire run."""
    events = _load_v3_events(repository=repository, run_id=run_id)

    chain_ids: set[str] = set()
    for event in events:
        cid = event.execution_chain_id or event.event_id
        chain_ids.add(cid)

    chain_views: list[ReplayChainView] = []
    for cid in sorted(chain_ids):
        chain_events = [
            e for e in events
            if (e.execution_chain_id or e.event_id) == cid
        ]
        root = chain_events[0] if chain_events else None
        skill_events = [
            e for e in chain_events
            if e.event_type in (EventType.SKILL_STARTED.value, EventType.SKILL_FINISHED.value, EventType.SKILL_FAILED.value)
        ]
        trigger_events = [
            e for e in chain_events
            if e.trigger_rule_id is not None
        ]
        chain_views.append(
            ReplayChainView(
                run_id=run_id,
                execution_chain_id=cid,
                root_event_id=root.event_id if root else "",
                events=[e.model_dump(mode="json") for e in chain_events],
                event_count=len(chain_events),
                skill_events=[e.model_dump(mode="json") for e in skill_events],
                trigger_events=[e.model_dump(mode="json") for e in trigger_events],
            )
        )

    available_targets = []
    for event in events:
        if event.event_type == EventType.SKILL_STARTED.value and event.trigger_rule_id:
            available_targets.append({
                "event_id": event.event_id,
                "chain_id": event.execution_chain_id or event.event_id,
                "skill_name": event.source,
                "trigger_rule_id": event.trigger_rule_id,
                "parent_event_id": event.parent_event_id,
            })

    return ReplayPlan(
        source_run_id=run_id,
        entry_type=ReplayEntryType.BY_RUN,
        available_targets=available_targets,
        chain_views=chain_views,
    )


async def replay_by_chain(
    *,
    repository: SQLiteTraceRepository,
    run_id: str,
    execution_chain_id: str,
    workspace_root: str | None = None,
    registry: SkillRegistry | None = None,
) -> ReplayPlan:
    """List available replay targets for a specific execution chain."""
    events = _load_v3_events(repository=repository, run_id=run_id)
    chain_events = [
        e for e in events
        if (e.execution_chain_id or e.event_id) == execution_chain_id
    ]

    root = chain_events[0] if chain_events else None
    skill_events = [
        e for e in chain_events
        if e.event_type in (EventType.SKILL_STARTED.value, EventType.SKILL_FINISHED.value, EventType.SKILL_FAILED.value)
    ]
    trigger_events = [
        e for e in chain_events
        if e.trigger_rule_id is not None
    ]

    chain_view = ReplayChainView(
        run_id=run_id,
        execution_chain_id=execution_chain_id,
        root_event_id=root.event_id if root else "",
        events=[e.model_dump(mode="json") for e in chain_events],
        event_count=len(chain_events),
        skill_events=[e.model_dump(mode="json") for e in skill_events],
        trigger_events=[e.model_dump(mode="json") for e in trigger_events],
    )

    available_targets = []
    for event in chain_events:
        if event.event_type == EventType.SKILL_STARTED.value and event.trigger_rule_id:
            available_targets.append({
                "event_id": event.event_id,
                "skill_name": event.source,
                "trigger_rule_id": event.trigger_rule_id,
                "parent_event_id": event.parent_event_id,
            })

    return ReplayPlan(
        source_run_id=run_id,
        entry_type=ReplayEntryType.BY_CHAIN,
        available_targets=available_targets,
        chain_views=[chain_view],
    )


async def replay_by_event(
    *,
    repository: SQLiteTraceRepository,
    run_id: str,
    event_id: str,
    workspace_root: str | None = None,
    registry: SkillRegistry | None = None,
    mode: ReplayMode = ReplayMode.FIRST_ACTION_REPLAY,
) -> ReplayResult:
    """Replay a specific event using the specified mode.

    Supported modes:
    - trace_replay: rebuild chain view without execution
    - event_replay: re-feed a historical event into a fresh runtime
    - first_action_replay: replay the first triggered skill (default, backward compatible)
    """
    events = _load_v3_events(repository=repository, run_id=run_id)
    source_event = next((event for event in events if event.event_id == event_id), None)
    if source_event is None:
        raise ValueError(f"未找到 event_id={event_id} 的 v3 event。")

    if mode == ReplayMode.TRACE_REPLAY:
        return _build_trace_replay_result(
            source_event=source_event, events=events
        )

    if mode == ReplayMode.EVENT_REPLAY:
        return await _execute_event_replay(
            source_event=source_event,
            events=events,
            workspace_root=workspace_root,
            registry=registry,
        )

    return await _execute_first_action_replay(
        source_event=source_event,
        events=events,
        workspace_root=workspace_root,
        registry=registry,
    )


def _build_trace_replay_result(
    *,
    source_event: V3Event,
    events: list[V3Event],
) -> ReplayResult:
    """Build a trace replay result that reconstructs the chain view."""
    chain_id = source_event.execution_chain_id or source_event.event_id
    chain_events = [
        e for e in events
        if (e.execution_chain_id or e.event_id) == chain_id
    ]
    chain_events.sort(key=lambda e: e.created_at)

    replay_run_id = str(uuid4())
    metadata = ReplayMetadata(
        replay_run_id=replay_run_id,
        source_run_id=source_event.run_id,
        source_event_id=source_event.event_id,
        execution_chain_id=chain_id,
        replay_mode=ReplayMode.TRACE_REPLAY.value,
        entry_type=ReplayEntryType.BY_EVENT.value,
        target_skill_name=source_event.source,
    )

    return ReplayResult(
        metadata=metadata,
        success=True,
        summary=f"Trace replay: reconstructed chain with {len(chain_events)} events",
        events=[e.model_dump(mode="json") for e in chain_events],
        trace=[],
    )


async def _execute_event_replay(
    *,
    source_event: V3Event,
    events: list[V3Event],
    workspace_root: str | None = None,
    registry: SkillRegistry | None = None,
) -> ReplayResult:
    """Re-feed a historical event into a fresh runtime."""
    replay_run_id = str(uuid4())
    event_bus = EventBus()
    event_store = EventStore()
    trace_events = attach_trace_collector(event_bus)
    skill_registry = registry or build_default_skill_registry(workspace_root=workspace_root)
    skill_executor = SkillExecutor(skill_registry)
    replay_rules = _build_replay_trigger_rules(
        source_event=source_event,
        events=events,
        registry=skill_registry,
    )
    if replay_rules:
        trigger_registry = TriggerRegistry()
        for rule in replay_rules:
            trigger_registry.register(rule)
        trigger_engine = TriggerEngine(
            trigger_registry=trigger_registry,
            skill_executor=skill_executor,
            event_bus=event_bus,
            event_store=event_store,
        )
        event_bus.subscribe(source_event.event_type, trigger_engine.handle_event)

    chain_id = source_event.execution_chain_id or source_event.event_id
    metadata = ReplayMetadata(
        replay_run_id=replay_run_id,
        source_run_id=source_event.run_id,
        source_event_id=source_event.event_id,
        execution_chain_id=chain_id,
        replay_mode=ReplayMode.EVENT_REPLAY.value,
        entry_type=ReplayEntryType.BY_EVENT.value,
        target_skill_name=source_event.source,
    )

    replay_event = V3Event(
        run_id=replay_run_id,
        event_type=source_event.event_type,
        source=source_event.source,
        parent_event_id=source_event.event_id,
        trigger_rule_id=source_event.trigger_rule_id,
        execution_chain_id=chain_id,
        trigger_depth=0,
        payload={
            "replay": metadata.model_dump(mode="json"),
            "source_run_id": source_event.run_id,
            "source_event_id": source_event.event_id,
            "original_payload": source_event.payload,
        },
        metadata={
            "replay_marker": metadata.model_dump(mode="json"),
        },
    )

    await _publish_replay_event(
        event_bus=event_bus,
        event_store=event_store,
        event=replay_event,
    )

    return ReplayResult(
        metadata=metadata,
        success=True,
        summary=f"Event replay: re-fed event {source_event.event_type} from {source_event.source}",
        output={"original_payload": source_event.payload},
        events=[e.model_dump(mode="json") for e in event_store.list()],
        trace=[e.model_dump(mode="json") for e in trace_events],
    )


async def _execute_first_action_replay(
    *,
    source_event: V3Event,
    events: list[V3Event],
    workspace_root: str | None = None,
    registry: SkillRegistry | None = None,
) -> ReplayResult:
    """Replay the first trigger-driven skill rooted at one source event."""
    replay_target = _resolve_replay_target(source_event=source_event, events=events)
    replay_run_id = str(uuid4())
    event_bus = EventBus()
    event_store = EventStore()
    trace_events = attach_trace_collector(event_bus)
    skill_registry = registry or build_default_skill_registry(workspace_root=workspace_root)
    skill_executor = SkillExecutor(skill_registry)

    metadata = ReplayMetadata(
        replay_run_id=replay_run_id,
        source_run_id=source_event.run_id,
        source_event_id=source_event.event_id,
        execution_chain_id=source_event.execution_chain_id or source_event.event_id,
        replay_mode=ReplayMode.FIRST_ACTION_REPLAY.value,
        entry_type=ReplayEntryType.BY_EVENT.value,
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
                "source_run_id": source_event.run_id,
                "source_event_id": source_event.event_id,
                "input_payload": replay_target["input_payload"],
            },
            metadata={
                "replay_marker": metadata.model_dump(mode="json"),
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
                "source_run_id": source_event.run_id,
                "source_event_id": source_event.event_id,
                "summary": output.summary,
                "error": output.error,
                "data": output.data,
            },
            metadata={
                "replay_marker": metadata.model_dump(mode="json"),
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


def _build_replay_trigger_rules(
    *,
    source_event: V3Event,
    events: list[V3Event],
    registry: SkillRegistry,
) -> list[TriggerRule]:
    """Build synthetic trigger rules from historical child skill starts."""
    historical_children = [
        child
        for child in events
        if child.parent_event_id == source_event.event_id
        and child.event_type == EventType.SKILL_STARTED.value
    ]
    historical_children.sort(key=lambda item: (item.created_at, item.event_id))
    rules: list[TriggerRule] = []
    for index, child in enumerate(historical_children):
        if registry.get(child.source) is None:
            continue
        raw_input_payload = child.payload.get("input_payload") if isinstance(child.payload, dict) else None
        rules.append(
            TriggerRule(
                rule_id=child.trigger_rule_id or f"replay-rule-{index}",
                event_type=source_event.event_type,
                target_skill_name=child.source,
                priority=index,
                once_per_run=True,
                input_mapping=dict(raw_input_payload) if isinstance(raw_input_payload, dict) else {},
            )
        )
    return rules


async def _publish_replay_event(*, event_bus: EventBus, event_store: EventStore, event: V3Event) -> None:
    event_store.append(event)
    await event_bus.publish(event)
