"""Tests for the V3 graph runtime."""

from __future__ import annotations

import asyncio

from app.v3.contracts.event_contracts import EventType
from app.v3.contracts.graph_contracts import TaskGraph, TaskNode
from app.v3.contracts.skill_contracts import SkillInput, SkillOutput, SkillSpec, SkillType
from app.v3.contracts.trigger_contracts import TriggerRule
from app.v3.events.event_bus import EventBus
from app.v3.events.event_store import EventStore
from app.v3.graph.graph_validator import GraphValidator
from app.v3.runtime.execution_kernel import ExecutionKernel
from app.v3.runtime.graph_executor import GraphExecutor
from app.v3.runtime.skill_executor import SkillExecutor
from app.v3.skills.base import Skill
from app.v3.skills.registry import SkillRegistry
from app.v3.trace.v3_trace import V3TraceCollector
from app.v3.trigger.trigger_engine import TriggerEngine
from app.v3.trigger.trigger_registry import TriggerRegistry


class EchoSkill(Skill):
    def __init__(self, name: str) -> None:
        super().__init__(
            SkillSpec(
                name=name,
                description=f"{name} skill",
                skill_type=SkillType.COMPOSITE,
                capabilities=[name],
            )
        )

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        return SkillOutput(
            success=True,
            summary=f"{self.spec.name} done",
            data={"payload": skill_input.payload, "context": skill_input.context},
        )


class RecordingSkill(Skill):
    def __init__(self) -> None:
        super().__init__(
            SkillSpec(
                name="recording",
                description="record trigger payload",
                skill_type=SkillType.COMPOSITE,
                capabilities=["record"],
            )
        )
        self.inputs: list[SkillInput] = []

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        self.inputs.append(skill_input)
        return SkillOutput(success=True, summary="recorded", data={"ok": True})


def test_v3_kernel_executes_serial_graph_and_collects_events() -> None:
    registry = SkillRegistry()
    registry.register(EchoSkill("analyze"))
    registry.register(EchoSkill("code"))
    event_bus = EventBus()
    event_store = EventStore()
    trace_collector = V3TraceCollector()

    async def trace_handler(event) -> None:
        trace_collector.record(event)

    for event_type in [
        EventType.GRAPH_STARTED.value,
        EventType.GRAPH_FINISHED.value,
        EventType.SKILL_STARTED.value,
        EventType.SKILL_FINISHED.value,
    ]:
        event_bus.subscribe(event_type, trace_handler)

    kernel = ExecutionKernel(
        graph_executor=GraphExecutor(
            skill_executor=SkillExecutor(registry),
            event_bus=event_bus,
            event_store=event_store,
        ),
        validator=GraphValidator(),
        event_bus=event_bus,
        event_store=event_store,
    )

    graph = TaskGraph(
        graph_id="graph-1",
        run_id="run-1",
        nodes=[
            TaskNode(node_id="analyze", skill_name="analyze"),
            TaskNode(
                node_id="code",
                skill_name="code",
                input_payload={"goal": "patch code"},
                dependencies=["analyze"],
            ),
        ],
    )

    context = asyncio.run(kernel.run_graph(graph))
    report = context.to_report(graph)

    assert report.status.value == "completed"
    assert report.completed_node_ids == ["analyze", "code"]
    assert report.failed_node_ids == []
    assert report.node_outputs["code"]["payload"]["goal"] == "patch code"
    assert [event.event_type for event in event_store.list()] == [
        "graph_started",
        "skill_started",
        "skill_finished",
        "skill_started",
        "skill_finished",
        "graph_finished",
    ]
    assert [event.event_type for event in trace_collector.list()] == [
        "graph_started",
        "skill_started",
        "skill_finished",
        "skill_started",
        "skill_finished",
        "graph_finished",
    ]


def test_trigger_engine_maps_event_payload_into_skill_input() -> None:
    registry = SkillRegistry()
    recording_skill = RecordingSkill()
    registry.register(recording_skill)
    engine = TriggerEngine(TriggerRegistry(), SkillExecutor(registry))
    engine.trigger_registry.register(
        TriggerRule(
            rule_id="rule-1",
            event_type="code_updated",
            target_skill_name="recording",
            input_mapping={
                "changed_files": "event.payload.changed_files",
                "kind": "event.event_type",
            },
        )
    )

    from app.v3.contracts.event_contracts import V3Event

    asyncio.run(
        engine.handle_event(
            V3Event(
                run_id="run-2",
                event_type="code_updated",
                source="coder",
                payload={"changed_files": ["app/v3/runtime/graph_executor.py"]},
            )
        )
    )

    assert len(recording_skill.inputs) == 1
    assert recording_skill.inputs[0].payload["changed_files"] == ["app/v3/runtime/graph_executor.py"]
    assert recording_skill.inputs[0].payload["kind"] == "code_updated"
