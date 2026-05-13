"""Tests for the V3 graph runtime."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routes.agent import (
    AgentInspectGraphRequest,
    AgentPlanRequest,
    AgentRunRequest,
    inspect_agent_graph,
    plan_agent,
    run_agent,
)
from app.db.sqlite import SQLiteDB
from app.trace.repository import SQLiteTraceRepository
from app.trace.viewer import load_and_format_timeline
from app.v3.contracts.event_contracts import EventType, V3Event
from app.v3.contracts.graph_contracts import TaskGraph, TaskNode
from app.v3.contracts.planning_contracts import PlanningResult, RecoveryStrategy
from app.v3.contracts.skill_contracts import SkillInput, SkillOutput, SkillSpec, SkillType
from app.v3.contracts.trigger_contracts import TriggerRule
from app.v3 import build_default_skill_registry
from app.v3.events.event_bus import EventBus
from app.v3.events.event_store import EventStore
from app.v3.graph.graph_validator import GraphValidator
from app.v3.runtime.execution_kernel import ExecutionKernel
from app.v3.runtime.graph_executor import GraphExecutor
from app.v3.runtime.skill_executor import SkillExecutor
from app.v3.runner import run_v3
from app.v3.skills.base import Skill
from app.v3.skills.registry import SkillRegistry
from app.v3.trace import attach_trace_collector
from app.v3.trigger.trigger_engine import TriggerEngine
from app.v3.trigger.trigger_registry import TriggerRegistry
from app.v3.adapters.v2_agent_adapter import V2AgentAdapter


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


class OrderedRecordingSkill(Skill):
    def __init__(self, name: str, sink: list[str]) -> None:
        super().__init__(
            SkillSpec(
                name=name,
                description=f"{name} recorder",
                skill_type=SkillType.COMPOSITE,
                capabilities=["record"],
            )
        )
        self.sink = sink

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        self.sink.append(self.spec.name)
        return SkillOutput(success=True, summary=f"{self.spec.name} recorded", data={"ok": True})


class FakeV2CoderAdapter(V2AgentAdapter):
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

        async def _run(payload: dict[str, object]) -> dict[str, object]:
            self.calls.append(payload)
            return {
                "summary": "Real V2 coder executed",
                "modified_files": ["app/example.py"],
                "created_files": [],
                "deleted_files": [],
                "diff_previews": {"app/example.py": "+print('patched')"},
                "patch_summary": "Patched through V2 coder",
            }

        super().__init__(_run)


class FakeExternalCoderAdapter(V2AgentAdapter):
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

        async def _run(payload: dict[str, object]) -> dict[str, object]:
            self.calls.append(payload)
            return {
                "summary": "External coder executed",
                "executor": "external",
                "modified_files": ["app/external.py"],
                "created_files": [],
                "deleted_files": [],
                "diff_previews": {"app/external.py": "+print('external patch')"},
                "patch_summary": "Patched through external coder",
            }

        super().__init__(_run)


class SleepSkill(Skill):
    def __init__(self, name: str, delay: float) -> None:
        super().__init__(
            SkillSpec(
                name=name,
                description=f"{name} sleeps",
                skill_type=SkillType.COMPOSITE,
                capabilities=[name],
            )
        )
        self.delay = delay

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        await asyncio.sleep(self.delay)
        return SkillOutput(success=True, summary=f"{self.spec.name} done", data={"ok": True})


def test_v3_kernel_executes_serial_graph_and_collects_events() -> None:
    registry = SkillRegistry()
    registry.register(EchoSkill("analyze"))
    registry.register(EchoSkill("code"))
    event_bus = EventBus()
    event_store = EventStore()
    trace_events = attach_trace_collector(event_bus)

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
    assert report.recovered_node_ids == []
    assert report.node_outputs["code"]["payload"]["goal"] == "patch code"
    assert [node.node_id for node in report.execution_nodes] == ["analyze", "code"]
    assert [event.event_type for event in event_store.list()] == [
        "graph_started",
        "skill_started",
        "skill_finished",
        "skill_started",
        "skill_finished",
        "graph_finished",
    ]
    assert [event.event_type for event in trace_events] == [
        "graph_started",
        "skill_started",
        "skill_finished",
        "skill_started",
        "skill_finished",
        "graph_finished",
    ]


def test_v3_kernel_supports_branch_and_join_execution() -> None:
    registry = SkillRegistry()
    registry.register(EchoSkill("root"))
    registry.register(EchoSkill("left"))
    registry.register(EchoSkill("right"))
    registry.register(EchoSkill("join"))
    kernel = ExecutionKernel(
        graph_executor=GraphExecutor(skill_executor=SkillExecutor(registry)),
        validator=GraphValidator(),
    )
    graph = TaskGraph(
        graph_id="graph-branch-join",
        run_id="run-branch-join",
        nodes=[
            TaskNode(node_id="root", skill_name="root"),
            TaskNode(node_id="left", skill_name="left", dependencies=["root"]),
            TaskNode(node_id="right", skill_name="right", dependencies=["root"]),
            TaskNode(node_id="join", skill_name="join", dependencies=["left", "right"]),
        ],
    )

    context = asyncio.run(kernel.run_graph(graph))
    report = context.to_report(graph)

    assert report.status.value == "completed"
    assert report.completed_node_ids == ["root", "left", "right", "join"]
    assert report.node_outputs["join"]["context"]["left"]["payload"] == {}
    assert report.node_outputs["join"]["context"]["right"]["payload"] == {}
    assert report.recovered_node_ids == []
    assert [node.node_id for node in report.execution_nodes] == ["root", "left", "right", "join"]


def test_v3_kernel_executes_ready_nodes_in_parallel() -> None:
    registry = SkillRegistry()
    registry.register(EchoSkill("root"))
    registry.register(SleepSkill("left", 0.2))
    registry.register(SleepSkill("right", 0.2))
    registry.register(EchoSkill("join"))
    kernel = ExecutionKernel(
        graph_executor=GraphExecutor(skill_executor=SkillExecutor(registry)),
        validator=GraphValidator(),
    )
    graph = TaskGraph(
        graph_id="graph-parallel",
        run_id="run-parallel",
        nodes=[
            TaskNode(node_id="root", skill_name="root"),
            TaskNode(node_id="left", skill_name="left", dependencies=["root"]),
            TaskNode(node_id="right", skill_name="right", dependencies=["root"]),
            TaskNode(node_id="join", skill_name="join", dependencies=["left", "right"]),
        ],
    )

    started_at = time.perf_counter()
    context = asyncio.run(kernel.run_graph(graph))
    elapsed = time.perf_counter() - started_at
    report = context.to_report(graph)

    assert report.status.value == "completed"
    assert elapsed < 0.35


def test_graph_validator_rejects_cycles() -> None:
    graph = TaskGraph(
        graph_id="graph-cycle",
        run_id="run-cycle",
        nodes=[
            TaskNode(node_id="a", skill_name="echo", dependencies=["c"]),
            TaskNode(node_id="b", skill_name="echo", dependencies=["a"]),
            TaskNode(node_id="c", skill_name="echo", dependencies=["b"]),
        ],
    )

    with pytest.raises(ValueError, match="cycle"):
        GraphValidator().validate(graph)


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


def test_trigger_engine_applies_rule_priority_order() -> None:
    sink: list[str] = []
    registry = SkillRegistry()
    registry.register(OrderedRecordingSkill("low_priority", sink))
    registry.register(OrderedRecordingSkill("high_priority", sink))
    trigger_registry = TriggerRegistry()
    trigger_registry.register(
        TriggerRule(
            rule_id="low",
            event_type="code_updated",
            target_skill_name="low_priority",
            priority=50,
        )
    )
    trigger_registry.register(
        TriggerRule(
            rule_id="high",
            event_type="code_updated",
            target_skill_name="high_priority",
            priority=10,
        )
    )
    engine = TriggerEngine(trigger_registry, SkillExecutor(registry))

    asyncio.run(
        engine.handle_event(
            V3Event(
                run_id="run-priority",
                event_type="code_updated",
                source="coder",
                payload={"changed_files": ["app/example.py"]},
            )
        )
    )

    assert sink == ["high_priority", "low_priority"]


def test_trigger_engine_can_suppress_repeated_triggers_with_dedupe_key() -> None:
    registry = SkillRegistry()
    recording_skill = RecordingSkill()
    registry.register(recording_skill)
    trigger_registry = TriggerRegistry()
    trigger_registry.register(
        TriggerRule(
            rule_id="dedupe",
            event_type="test_failed",
            target_skill_name="recording",
            suppress_repeats=True,
            dedupe_key_template="event.payload.node_id",
        )
    )
    engine = TriggerEngine(trigger_registry, SkillExecutor(registry))

    event_one = V3Event(
        run_id="run-dedupe",
        event_type="test_failed",
        source="test_runner",
        payload={"node_id": "test_runner", "failure_type": "assertion_error"},
    )
    event_two = V3Event(
        run_id="run-dedupe",
        event_type="test_failed",
        source="test_runner",
        payload={"node_id": "test_runner", "failure_type": "assertion_error"},
    )

    asyncio.run(engine.handle_event(event_one))
    asyncio.run(engine.handle_event(event_two))

    assert len(recording_skill.inputs) == 1


def test_trigger_engine_can_limit_rule_to_once_per_run() -> None:
    registry = SkillRegistry()
    recording_skill = RecordingSkill()
    registry.register(recording_skill)
    trigger_registry = TriggerRegistry()
    trigger_registry.register(
        TriggerRule(
            rule_id="once",
            event_type="test_failed",
            target_skill_name="recording",
            once_per_run=True,
        )
    )
    engine = TriggerEngine(trigger_registry, SkillExecutor(registry))

    asyncio.run(
        engine.handle_event(
            V3Event(
                run_id="run-once",
                event_type="test_failed",
                source="test_runner",
                payload={"node_id": "test_runner_a"},
            )
        )
    )
    asyncio.run(
        engine.handle_event(
            V3Event(
                run_id="run-once",
                event_type="test_failed",
                source="test_runner",
                payload={"node_id": "test_runner_b"},
            )
        )
    )

    assert len(recording_skill.inputs) == 1


def test_trigger_engine_can_apply_cooldown_within_one_run(monkeypatch) -> None:
    registry = SkillRegistry()
    recording_skill = RecordingSkill()
    registry.register(recording_skill)
    trigger_registry = TriggerRegistry()
    trigger_registry.register(
        TriggerRule(
            rule_id="cooldown",
            event_type="test_failed",
            target_skill_name="recording",
            cooldown_key="event.payload.node_id",
            cooldown_seconds=30.0,
        )
    )
    engine = TriggerEngine(trigger_registry, SkillExecutor(registry))

    current_time = {"value": 100.0}
    monkeypatch.setattr("app.v3.trigger.trigger_engine.time.monotonic", lambda: current_time["value"])

    asyncio.run(
        engine.handle_event(
            V3Event(
                run_id="run-cooldown",
                event_type="test_failed",
                source="test_runner",
                payload={"node_id": "test_runner"},
            )
        )
    )
    current_time["value"] = 110.0
    asyncio.run(
        engine.handle_event(
            V3Event(
                run_id="run-cooldown",
                event_type="test_failed",
                source="test_runner",
                payload={"node_id": "test_runner"},
            )
        )
    )

    assert len(recording_skill.inputs) == 1


def test_trigger_engine_records_governance_metadata_on_trigger_execution(monkeypatch) -> None:
    registry = SkillRegistry()
    recording_skill = RecordingSkill()
    registry.register(recording_skill)
    execution_nodes = []
    event_store = EventStore()
    trigger_registry = TriggerRegistry()
    trigger_registry.register(
        TriggerRule(
            rule_id="governed",
            event_type="test_failed",
            target_skill_name="recording",
            suppress_repeats=True,
            dedupe_key_template="event.payload.node_id",
            cooldown_key="event.payload.node_id",
            cooldown_seconds=10.0,
            priority=5,
        )
    )
    engine = TriggerEngine(
        trigger_registry,
        SkillExecutor(registry),
        event_store=event_store,
        execution_nodes=execution_nodes,
    )
    monkeypatch.setattr("app.v3.trigger.trigger_engine.time.monotonic", lambda: 500.0)

    asyncio.run(
        engine.handle_event(
            V3Event(
                run_id="run-governed",
                event_type="test_failed",
                source="test_runner",
                payload={"node_id": "test_runner"},
            )
        )
    )

    governance = execution_nodes[0].output_data["trigger_governance"]
    assert governance["dedupe_key"] == "governed:test_runner"
    assert governance["cooldown_key"] == "governed:test_runner"
    assert governance["cooldown_seconds"] == 10.0


def test_trigger_engine_publishes_trigger_skipped_event_for_cooldown(monkeypatch) -> None:
    registry = SkillRegistry()
    recording_skill = RecordingSkill()
    registry.register(recording_skill)
    event_store = EventStore()
    trigger_registry = TriggerRegistry()
    trigger_registry.register(
        TriggerRule(
            rule_id="cooldown",
            event_type="test_failed",
            target_skill_name="recording",
            cooldown_key="event.payload.node_id",
            cooldown_seconds=30.0,
        )
    )
    engine = TriggerEngine(trigger_registry, SkillExecutor(registry), event_store=event_store)

    current_time = {"value": 700.0}
    monkeypatch.setattr("app.v3.trigger.trigger_engine.time.monotonic", lambda: current_time["value"])

    first = V3Event(
        run_id="run-cooldown-skip",
        event_type="test_failed",
        source="test_runner",
        payload={"node_id": "test_runner"},
    )
    second = V3Event(
        run_id="run-cooldown-skip",
        event_type="test_failed",
        source="test_runner",
        payload={"node_id": "test_runner"},
    )

    asyncio.run(engine.handle_event(first))
    current_time["value"] = 705.0
    asyncio.run(engine.handle_event(second))

    skipped = [event for event in event_store.list() if event.event_type == EventType.TRIGGER_SKIPPED.value]
    assert len(skipped) == 1
    assert skipped[0].payload["skip_reason"] == "cooldown"
    assert skipped[0].payload["cooldown_key"] == "cooldown:test_runner"


def test_run_v3_report_includes_trigger_diagnostics_for_skipped_trigger(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_fail.py").write_text(
        "def test_fail():\n    assert False\n",
        encoding="utf-8",
    )
    registry = build_default_skill_registry(workspace_root=tmp_path)
    recording_skill = RecordingSkill()
    registry.register(recording_skill)

    result = asyncio.run(
        run_v3(
            goal="run tests",
            workdir=str(tmp_path),
            include_events=True,
            include_trace=True,
            registry=registry,
            trigger_rules=[
                TriggerRule(
                    rule_id="cooldown",
                    event_type=EventType.TEST_FAILED.value,
                    target_skill_name="recording",
                    cooldown_key="event.payload.node_id",
                    cooldown_seconds=30.0,
                )
            ],
        )
    )

    diagnostics = result["report"].trigger_diagnostics
    assert diagnostics
    assert diagnostics[0].status == "executed"
    assert diagnostics[0].trigger_rule_id == "cooldown"
    assert diagnostics[0].cooldown_key == "cooldown:test_runner"


def test_trigger_engine_records_skipped_trigger_diagnostic(monkeypatch) -> None:
    registry = SkillRegistry()
    recording_skill = RecordingSkill()
    registry.register(recording_skill)
    diagnostics = []
    trigger_registry = TriggerRegistry()
    trigger_registry.register(
        TriggerRule(
            rule_id="cooldown",
            event_type="test_failed",
            target_skill_name="recording",
            cooldown_key="event.payload.node_id",
            cooldown_seconds=30.0,
        )
    )
    engine = TriggerEngine(
        trigger_registry,
        SkillExecutor(registry),
        diagnostics=diagnostics,
    )

    current_time = {"value": 900.0}
    monkeypatch.setattr("app.v3.trigger.trigger_engine.time.monotonic", lambda: current_time["value"])

    first = V3Event(
        run_id="run-diagnostics",
        event_type="test_failed",
        source="test_runner",
        payload={"node_id": "test_runner"},
    )
    second = V3Event(
        run_id="run-diagnostics",
        event_type="test_failed",
        source="test_runner",
        payload={"node_id": "test_runner"},
    )

    asyncio.run(engine.handle_event(first))
    current_time["value"] = 905.0
    asyncio.run(engine.handle_event(second))

    assert len(diagnostics) == 2
    assert diagnostics[0].status == "executed"
    assert diagnostics[1].status == "skipped"
    assert diagnostics[1].skip_reason == "cooldown"
    assert diagnostics[1].cooldown_key == "cooldown:test_runner"


def test_trigger_engine_allows_trigger_after_cooldown_window(monkeypatch) -> None:
    registry = SkillRegistry()
    recording_skill = RecordingSkill()
    registry.register(recording_skill)
    trigger_registry = TriggerRegistry()
    trigger_registry.register(
        TriggerRule(
            rule_id="cooldown",
            event_type="test_failed",
            target_skill_name="recording",
            cooldown_key="event.payload.node_id",
            cooldown_seconds=5.0,
        )
    )
    engine = TriggerEngine(trigger_registry, SkillExecutor(registry))

    current_time = {"value": 200.0}
    monkeypatch.setattr("app.v3.trigger.trigger_engine.time.monotonic", lambda: current_time["value"])

    asyncio.run(
        engine.handle_event(
            V3Event(
                run_id="run-cooldown-open",
                event_type="test_failed",
                source="test_runner",
                payload={"node_id": "test_runner"},
            )
        )
    )
    current_time["value"] = 206.0
    asyncio.run(
        engine.handle_event(
            V3Event(
                run_id="run-cooldown-open",
                event_type="test_failed",
                source="test_runner",
                payload={"node_id": "test_runner"},
            )
        )
    )

    assert len(recording_skill.inputs) == 2


def test_planning_skill_generates_repo_aware_graph(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )
    registry = build_default_skill_registry(workspace_root=tmp_path)
    planning = registry.get("planning")

    output = asyncio.run(
        planning.execute(
            SkillInput(
                run_id="run-plan",
                payload={"goal": "修复一个 bug 并运行测试", "workspace_root": str(tmp_path)},
                context={"workspace_root": str(tmp_path)},
            )
        )
    )

    planning_result = PlanningResult.model_validate(output.data)
    graph = planning_result.graph.model_dump(mode="json")
    assert output.success is True
    assert planning_result.repo_profile == "python_pytest"
    assert planning_result.recovery_strategy == RecoveryStrategy.FIX_AND_RETEST
    assert planning_result.template_name == "default"
    assert "default linear graph" in planning_result.template_reason
    assert planning_result.planner_notes
    assert [node["node_id"] for node in graph["nodes"]] == ["analyze_repo", "coding", "test_runner"]
    assert graph["nodes"][2]["input_payload"]["command"] == "pytest -q"
    trigger_rules = planning_result.trigger_rules
    assert len(trigger_rules) == 1
    assert trigger_rules[0].event_type == EventType.TEST_FAILED.value
    assert trigger_rules[0].target_skill_name == "tdd"
    assert trigger_rules[0].input_mapping["resume_from_failure"] is True


def test_planning_skill_can_include_retrieve_docs_and_external_coding_mode(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )
    registry = build_default_skill_registry(workspace_root=tmp_path)
    planning = registry.get("planning")

    output = asyncio.run(
        planning.execute(
            SkillInput(
                run_id="run-plan-rag-external",
                payload={
                    "goal": "use docs knowledge to fix bug and run tests",
                    "workspace_root": str(tmp_path),
                    "rag_ids": ["default", "course"],
                    "coding_execution_mode": "external",
                    "preferred_agent": "codex_cli",
                },
                context={"workspace_root": str(tmp_path)},
            )
        )
    )

    planning_result = PlanningResult.model_validate(output.data)
    graph = planning_result.graph.model_dump(mode="json")

    assert planning_result.rag_ids == ["default", "course"]
    assert planning_result.coding_execution_mode == "external"
    assert graph["nodes"][0]["node_id"] == "retrieve_docs"
    assert graph["nodes"][1]["node_id"] == "analyze_repo"
    assert graph["nodes"][2]["input_payload"]["execution_mode"] == "external"
    assert graph["nodes"][2]["input_payload"]["preferred_agent"] == "codex_cli"


def test_planning_skill_can_choose_fix_only_recovery_template(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )
    registry = build_default_skill_registry(workspace_root=tmp_path)
    planning = registry.get("planning")

    output = asyncio.run(
        planning.execute(
            SkillInput(
                run_id="run-plan-fix-only",
                payload={"goal": "fix only this bug, 不要重跑测试", "workspace_root": str(tmp_path)},
                context={"workspace_root": str(tmp_path)},
            )
        )
    )

    planning_result = PlanningResult.model_validate(output.data)
    trigger_rules = planning_result.trigger_rules
    assert len(trigger_rules) == 1
    assert trigger_rules[0].target_skill_name == "coding"
    assert planning_result.recovery_strategy == RecoveryStrategy.FIX_ONLY
    assert "resume_from_failure" not in trigger_rules[0].input_mapping


def test_planning_skill_can_generate_branch_testing_template(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
    (tmp_path / "tests" / "test_b.py").write_text("def test_b():\n    assert True\n", encoding="utf-8")
    registry = build_default_skill_registry(workspace_root=tmp_path)
    planning = registry.get("planning")

    output = asyncio.run(
        planning.execute(
            SkillInput(
                run_id="run-plan-branch",
                payload={"goal": "run all tests with branch verification", "workspace_root": str(tmp_path)},
                context={"workspace_root": str(tmp_path)},
            )
        )
    )

    planning_result = PlanningResult.model_validate(output.data)
    assert planning_result.template_name == "testing_branch_verify"
    assert "fans out focused test nodes" in planning_result.template_reason
    assert any("Selected branch verification template" in note for note in planning_result.planner_notes)
    assert planning_result.candidate_test_targets[:2] == ["tests/test_a.py", "tests/test_b.py"]
    assert [node.node_id for node in planning_result.graph.nodes] == [
        "analyze_repo",
        "test_scope_1",
        "test_scope_2",
        "test_full_suite",
    ]


def test_test_runner_skill_executes_pytest_via_v1_adapter(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )
    registry = build_default_skill_registry(workspace_root=tmp_path)
    test_runner = registry.get("test_runner")

    output = asyncio.run(
        test_runner.execute(
            SkillInput(
                run_id="run-test",
                payload={
                    "workspace_root": str(tmp_path),
                    "command": "pytest -q tests/test_sample.py",
                },
                context={"workspace_root": str(tmp_path)},
            )
        )
    )

    assert output.success is True
    assert output.data["executed_command"] == "pytest -q tests/test_sample.py"


def test_coding_skill_uses_v2_agent_adapter_when_available() -> None:
    adapter = FakeV2CoderAdapter()
    skill = build_default_skill_registry().get("coding")
    skill.internal_agent_adapter = adapter

    output = asyncio.run(
        skill.execute(
            SkillInput(
                run_id="run-coding",
                payload={"goal": "patch a file", "workspace_root": "."},
                context={
                    "workspace_root": ".",
                    "analyze_repo": {"repo_profile": "python_pytest"},
                    "last_test_result": {"summary": "test failed", "executed_command": "pytest -q"},
                },
            )
        )
    )

    assert output.success is True
    assert output.data["modified_files"] == ["app/example.py"]
    assert adapter.calls[0]["goal"] == "patch a file"
    assert output.data["execution_mode"] == "internal"


def test_coding_skill_can_use_external_execution_mode() -> None:
    internal_adapter = FakeV2CoderAdapter()
    external_adapter = FakeExternalCoderAdapter()
    skill = build_default_skill_registry().get("coding")
    skill.internal_agent_adapter = internal_adapter
    skill.external_agent_adapter = external_adapter

    output = asyncio.run(
        skill.execute(
            SkillInput(
                run_id="run-coding-external",
                payload={
                    "goal": "patch a file through external coder",
                    "workspace_root": ".",
                    "execution_mode": "external",
                    "preferred_agent": "codex_cli",
                },
                context={
                    "workspace_root": ".",
                    "analyze_repo": {"repo_profile": "python_pytest"},
                },
            )
        )
    )

    assert output.success is True
    assert output.data["execution_mode"] == "external"
    assert output.data["executor"] == "external"
    assert external_adapter.calls[0]["preferred_agent"] == "codex_cli"
    assert internal_adapter.calls == []


def test_retrieve_docs_skill_supports_multi_rag_via_adapter() -> None:
    async def fake_docs_tool(payload: dict[str, object]) -> dict[str, object]:
        return {
            "ok": True,
            "query": payload["query"],
            "rag_id": None,
            "rag_ids": payload["rag_ids"],
            "match_count": 2,
            "matches": [
                {"source": "docs/a.md", "content": "A"},
                {"source": "docs/b.md", "content": "B"},
            ],
        }

    registry = build_default_skill_registry()
    retrieve_skill = registry.get("retrieve_docs")
    retrieve_skill.docs_adapter.v1_tool_func = fake_docs_tool

    output = asyncio.run(
        retrieve_skill.execute(
            SkillInput(
                run_id="run-retrieve",
                payload={
                    "query": "how to apply patch",
                    "rag_ids": ["default", "course"],
                    "top_k": 2,
                },
                context={},
            )
        )
    )

    assert output.success is True
    assert output.data["rag_ids"] == ["default", "course"]
    assert output.data["match_count"] == 2


def test_tdd_skill_can_resume_from_failed_test_event() -> None:
    class FakeTestSkill(Skill):
        def __init__(self) -> None:
            super().__init__(
                SkillSpec(
                    name="test_runner",
                    description="fake test runner",
                    skill_type=SkillType.TOOL,
                    capabilities=["test.run"],
                )
            )
            self.calls = 0

        async def execute(self, skill_input: SkillInput) -> SkillOutput:
            self.calls += 1
            return SkillOutput(
                success=True,
                summary="tests passed",
                data={"executed_command": skill_input.payload.get("command", "pytest -q")},
            )

    class FakeCodingSkill(Skill):
        def __init__(self) -> None:
            super().__init__(
                SkillSpec(
                    name="coding",
                    description="fake coding",
                    skill_type=SkillType.COMPOSITE,
                    capabilities=["code.modify"],
                )
            )
            self.inputs: list[SkillInput] = []

        async def execute(self, skill_input: SkillInput) -> SkillOutput:
            self.inputs.append(skill_input)
            return SkillOutput(
                success=True,
                summary="patched",
                data={"changed_files": ["calc.py"]},
            )

    registry = SkillRegistry()
    fake_test = FakeTestSkill()
    fake_coding = FakeCodingSkill()
    registry.register(fake_test)
    registry.register(fake_coding)
    tdd_skill = build_default_skill_registry().get("tdd")
    tdd_skill.skill_executor = SkillExecutor(registry)

    output = asyncio.run(
        tdd_skill.execute(
            SkillInput(
                run_id="run-tdd",
                payload={
                    "command": "pytest -q tests/test_calc.py",
                    "workspace_root": ".",
                    "resume_from_failure": True,
                },
                context={
                    "source_event": {
                        "event_type": EventType.TEST_FAILED.value,
                        "payload": {
                            "executed_command": "pytest -q tests/test_calc.py",
                            "failure_type": "assertion_error",
                        },
                    }
                },
            )
        )
    )

    assert output.success is True
    assert fake_test.calls == 1
    assert len(fake_coding.inputs) == 1
    assert fake_coding.inputs[0].context["last_test_result"]["error"] == "assertion_error"


def test_tdd_skill_stops_when_coding_produces_no_changes() -> None:
    class FakeTestSkill(Skill):
        def __init__(self) -> None:
            super().__init__(
                SkillSpec(
                    name="test_runner",
                    description="fake test runner",
                    skill_type=SkillType.TOOL,
                    capabilities=["test.run"],
                )
            )

        async def execute(self, skill_input: SkillInput) -> SkillOutput:
            return SkillOutput(success=True, summary="tests passed", data={"executed_command": "pytest -q"})

    class NoChangeCodingSkill(Skill):
        def __init__(self) -> None:
            super().__init__(
                SkillSpec(
                    name="coding",
                    description="no-op coding",
                    skill_type=SkillType.COMPOSITE,
                    capabilities=["code.modify"],
                )
            )

        async def execute(self, skill_input: SkillInput) -> SkillOutput:
            return SkillOutput(success=True, summary="no-op", data={"changed_files": []})

    registry = SkillRegistry()
    registry.register(FakeTestSkill())
    registry.register(NoChangeCodingSkill())
    tdd_skill = build_default_skill_registry().get("tdd")
    tdd_skill.skill_executor = SkillExecutor(registry)

    output = asyncio.run(
        tdd_skill.execute(
            SkillInput(
                run_id="run-tdd-nochange",
                payload={"command": "pytest -q", "resume_from_failure": True},
                context={
                    "source_event": {
                        "event_type": EventType.TEST_FAILED.value,
                        "payload": {
                            "executed_command": "pytest -q",
                            "failure_type": "assertion_error",
                        },
                    }
                },
            )
        )
    )

    assert output.success is False
    assert output.error == "no_code_changes"


def test_tdd_skill_reports_when_focused_verification_passes_but_full_suite_fails() -> None:
    class SequencedTestSkill(Skill):
        def __init__(self) -> None:
            super().__init__(
                SkillSpec(
                    name="test_runner",
                    description="sequenced test runner",
                    skill_type=SkillType.TOOL,
                    capabilities=["test.run"],
                )
            )
            self.commands: list[str] = []

        async def execute(self, skill_input: SkillInput) -> SkillOutput:
            command = str(skill_input.payload.get("command") or "")
            self.commands.append(command)
            if command == "pytest -q tests/test_scope.py":
                return SkillOutput(success=True, summary="focused tests passed", data={"executed_command": command})
            return SkillOutput(
                success=False,
                summary=f"Tests failed: {command}",
                error="assertion_error",
                data={"executed_command": command, "failure_type": "assertion_error"},
            )

    class ChangingCodingSkill(Skill):
        def __init__(self) -> None:
            super().__init__(
                SkillSpec(
                    name="coding",
                    description="coding with changes",
                    skill_type=SkillType.COMPOSITE,
                    capabilities=["code.modify"],
                )
            )

        async def execute(self, skill_input: SkillInput) -> SkillOutput:
            return SkillOutput(
                success=True,
                summary="patched",
                data={"changed_files": ["app/example.py"]},
            )

    registry = SkillRegistry()
    registry.register(SequencedTestSkill())
    registry.register(ChangingCodingSkill())
    tdd_skill = build_default_skill_registry().get("tdd")
    tdd_skill.skill_executor = SkillExecutor(registry)

    output = asyncio.run(
        tdd_skill.execute(
            SkillInput(
                run_id="run-tdd-branch-summary",
                payload={
                    "command": "pytest -q",
                    "resume_from_failure": True,
                    "preferred_test_targets": ["tests/test_scope.py"],
                    "verify_full_suite": True,
                },
                context={
                    "source_event": {
                        "event_type": EventType.TEST_FAILED.value,
                        "payload": {
                            "executed_command": "pytest -q",
                            "failure_type": "assertion_error",
                        },
                    },
                    "analyze_repo": {
                        "candidate_test_commands": ["pytest -q tests/test_scope.py", "pytest -q"],
                    },
                },
            )
        )
    )

    assert output.success is False
    assert output.summary == "Focused verification passed, but full-suite verification still failed"
    branch = output.data["verification_branch_summary"]
    assert branch["failed_stage"] == "full_suite"
    assert branch["focused_commands_passed"] == ["pytest -q tests/test_scope.py"]


def test_run_v3_recovery_flow_can_fix_code_and_retest_in_temp_workspace(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "calc.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a - b\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_calc.py").write_text(
        (
            "import sys\n"
            "from pathlib import Path\n\n"
            "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
            "from calc import add\n\n\n"
            "def test_add():\n"
            "    assert add(2, 3) == 5\n"
        ),
        encoding="utf-8",
    )
    registry = build_default_skill_registry(workspace_root=tmp_path)

    class FileFixSkill(Skill):
        def __init__(self) -> None:
            super().__init__(
                SkillSpec(
                    name="coding",
                    description="apply deterministic calc fix",
                    skill_type=SkillType.COMPOSITE,
                    capabilities=["code.modify"],
                )
            )

        async def execute(self, skill_input: SkillInput) -> SkillOutput:
            workspace_root = Path(str(skill_input.payload.get("workspace_root") or tmp_path))
            target = workspace_root / "calc.py"
            target.write_text(
                "def add(a: int, b: int) -> int:\n    return a + b\n",
                encoding="utf-8",
            )
            future_timestamp = time.time() + 2
            os.utime(target, (future_timestamp, future_timestamp))
            return SkillOutput(
                success=True,
                summary="calc.py fixed",
                data={
                    "changed_files": ["calc.py"],
                    "patch_summary": "Updated add() to use addition",
                },
            )

    registry.register(FileFixSkill())

    result = asyncio.run(
        run_v3(
            goal="run tests and recover",
            workdir=str(tmp_path),
            include_events=True,
            include_trace=True,
            registry=registry,
        )
    )

    assert result["report"].status.value == "completed"
    assert result["report"].recovered_node_ids == ["test_runner"]
    trigger_nodes = [node for node in result["report"].execution_nodes if node.kind == "trigger"]
    assert len(trigger_nodes) == 1
    assert trigger_nodes[0].skill_name == "tdd"
    assert "Updated add() to use addition" in trigger_nodes[0].output_data["coding_result"]["patch_summary"]
    assert (tmp_path / "calc.py").read_text(encoding="utf-8").strip().endswith("return a + b")
    passed_retest = any(
        event["event_type"] == EventType.SKILL_FINISHED.value
        and event["source"] == "tdd"
        for event in result["events"]
    )
    assert passed_retest is True


def test_run_v3_shared_runner_returns_report_events_and_trace(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )

    result = asyncio.run(
        run_v3(
            goal="run tests",
            workdir=str(tmp_path),
            include_events=True,
            include_trace=True,
        )
    )

    assert result["report"].status.value == "completed"
    assert result["report"].completed_node_ids == ["analyze_repo", "test_runner"]
    assert result["report"].shared_state["planning"]["recovery_strategy"] == "fix_and_retest"
    assert result["report"].shared_state["planning"]["execution_layers"] == [["analyze_repo"], ["test_runner"]]
    assert len(result["events"]) >= 4
    assert len(result["trace"]) >= 4


def test_unified_run_agent_supports_v3_plan_only(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )

    response = run_agent(
        AgentRunRequest(
            version="v3",
            task="run tests",
            workdir=str(tmp_path),
            plan_only=True,
        )
    )

    assert response.report is None
    assert response.planning is not None
    assert response.inspection is not None
    assert response.planning.recovery_strategy == RecoveryStrategy.FIX_AND_RETEST
    assert response.inspection.execution_layers == [["analyze_repo"], ["test_runner"]]


def test_v3_plan_route_returns_structured_planning_result(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )

    response = asyncio.run(
        plan_agent(
            AgentPlanRequest(
                task="修复一个 bug 并运行测试",
                workdir=str(tmp_path),
            )
        )
    )

    assert response.planning.repo_profile == "python_pytest"
    assert response.planning.recovery_strategy == RecoveryStrategy.FIX_AND_RETEST
    assert response.planning.graph.nodes[-1].skill_name == "test_runner"


def test_v3_plan_route_supports_rag_and_external_coding_mode(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )

    response = asyncio.run(
        plan_agent(
            AgentPlanRequest(
                task="use docs knowledge to fix bug",
                workdir=str(tmp_path),
                rag_ids=["default", "course"],
                v3_coding_execution_mode="external",
            )
        )
    )

    assert response.planning.rag_ids == ["default", "course"]
    assert response.planning.coding_execution_mode == "external"
    assert response.planning.graph.nodes[0].skill_name == "retrieve_docs"


def test_v3_plan_route_accepts_goal_alias(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )

    response = asyncio.run(
        plan_agent(
            AgentPlanRequest(
                goal="run tests",
                workdir=str(tmp_path),
            )
        )
    )

    assert response.planning.goal_kind == "testing"
    assert response.planning.recovery_strategy == RecoveryStrategy.FIX_AND_RETEST


def test_v3_inspect_graph_route_returns_execution_layers(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )

    response = asyncio.run(
        inspect_agent_graph(
            AgentInspectGraphRequest(
                task="run tests",
                workdir=str(tmp_path),
            )
        )
    )

    assert response.inspection.is_valid is True
    assert response.inspection.execution_layers[0] == ["analyze_repo"]
    assert response.planning is not None
    assert response.planning.recovery_strategy == RecoveryStrategy.FIX_AND_RETEST


def test_v3_inspect_graph_route_accepts_goal_alias(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )

    response = asyncio.run(
        inspect_agent_graph(
            AgentInspectGraphRequest(
                goal="run tests",
                workdir=str(tmp_path),
            )
        )
    )

    assert response.inspection.is_valid is True
    assert response.planning is not None
    assert response.planning.goal_kind == "testing"


def test_v3_inspect_graph_route_requires_goal_or_graph() -> None:
    with pytest.raises(ValidationError):
        AgentInspectGraphRequest()


def test_run_v3_uses_planning_skill_recovery_template_without_manual_trigger_rules(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_fail.py").write_text(
        "def test_fail():\n    assert False\n",
        encoding="utf-8",
    )
    registry = build_default_skill_registry(workspace_root=tmp_path)
    recording_skill = RecordingSkill()
    registry.register(recording_skill)
    planning = registry.get("planning")
    original_execute = planning.execute

    async def patched_execute(skill_input: SkillInput) -> SkillOutput:
        output = await original_execute(skill_input)
        data = dict(output.data)
        data["trigger_rules"] = [
            {
                "rule_id": "template_fix_after_test_failed",
                "event_type": EventType.TEST_FAILED.value,
                "target_skill_name": "recording",
                "enabled": True,
                "input_mapping": {
                    "failure_type": "event.payload.failure_type",
                    "command": "event.payload.executed_command",
                },
            }
        ]
        return SkillOutput(success=True, summary=output.summary, data=data)

    planning.execute = patched_execute  # type: ignore[method-assign]

    result = asyncio.run(
        run_v3(
            goal="run tests and recover",
            workdir=str(tmp_path),
            include_events=True,
            include_trace=True,
            registry=registry,
        )
    )

    assert result["report"].status.value == "completed"
    assert result["report"].recovered_node_ids == ["test_runner"]
    trigger_nodes = [node for node in result["report"].execution_nodes if node.kind == "trigger"]
    assert len(trigger_nodes) == 1
    assert trigger_nodes[0].skill_name == "recording"
    assert len(recording_skill.inputs) == 1


def test_run_v3_connects_trigger_engine_to_event_bus(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_fail.py").write_text(
        "def test_fail():\n    assert False\n",
        encoding="utf-8",
    )
    registry = build_default_skill_registry(workspace_root=tmp_path)
    recording_skill = RecordingSkill()
    registry.register(recording_skill)

    result = asyncio.run(
        run_v3(
            goal="run tests",
            workdir=str(tmp_path),
            include_events=True,
            include_trace=True,
            registry=registry,
            trigger_rules=[
                TriggerRule(
                    rule_id="trigger-test-failed",
                    event_type=EventType.TEST_FAILED.value,
                    target_skill_name="recording",
                    input_mapping={
                        "failure_type": "event.payload.failure_type",
                        "command": "event.payload.executed_command",
                    },
                )
            ],
        )
    )

    assert result["report"].status.value == "completed"
    assert any(event["event_type"] == EventType.TEST_FAILED.value for event in result["events"])
    assert any(
        event["event_type"] == EventType.SKILL_STARTED.value and event["source"] == "recording"
        for event in result["events"]
    )
    assert result["report"].failed_node_ids == []
    assert result["report"].recovered_node_ids == ["test_runner"]
    trigger_nodes = [node for node in result["report"].execution_nodes if node.kind == "trigger"]
    assert len(trigger_nodes) == 1
    assert trigger_nodes[0].skill_name == "recording"
    assert trigger_nodes[0].source_event_type == EventType.TEST_FAILED.value
    assert trigger_nodes[0].parent_node_id == "test_runner"
    graph_test_node = next(node for node in result["report"].execution_nodes if node.node_id == "test_runner")
    assert graph_test_node.status == "recovered"
    assert len(recording_skill.inputs) == 1
    assert recording_skill.inputs[0].payload["command"] == "pytest -q"
    assert recording_skill.inputs[0].payload["failure_type"] is not None


def test_v3_trace_can_be_persisted_and_viewed_through_shared_trace_layer(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )
    trace_db = SQLiteDB(tmp_path / "trace.sqlite3")
    monkeypatch.setattr("app.v3.runner.SQLiteDB", lambda: trace_db)

    result = asyncio.run(
        run_v3(
            goal="run tests",
            workdir=str(tmp_path),
            include_events=True,
            include_trace=True,
        )
    )

    run_id = result["report"].run_id
    repository = SQLiteTraceRepository(trace_db)
    loaded = repository.query_timeline(run_id)
    rendered = load_and_format_timeline(repository, run_id)

    assert len(loaded) >= 4
    assert loaded[0].event_type == "graph_started"
    assert "graph_started" in rendered
    assert f"run_id={run_id}" in rendered
