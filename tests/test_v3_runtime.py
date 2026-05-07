"""Tests for the V3 graph runtime."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.db.sqlite import SQLiteDB
from app.trace.repository import SQLiteTraceRepository
from app.trace.viewer import load_and_format_timeline
from app.v3.contracts.event_contracts import EventType, V3Event
from app.v3.contracts.graph_contracts import TaskGraph, TaskNode
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
    assert report.node_outputs["code"]["payload"]["goal"] == "patch code"
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

    graph = output.data["graph"]
    assert output.success is True
    assert output.data["repo_profile"] == "python_pytest"
    assert [node["node_id"] for node in graph["nodes"]] == ["analyze_repo", "coding", "test_runner"]
    assert graph["nodes"][2]["input_payload"]["command"] == "pytest -q"


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
    skill.agent_adapter = adapter

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
    assert len(result["events"]) >= 4
    assert len(result["trace"]) >= 4


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

    assert result["report"].status.value == "partial_completed"
    assert any(event["event_type"] == EventType.TEST_FAILED.value for event in result["events"])
    assert any(
        event["event_type"] == EventType.SKILL_STARTED.value and event["source"] == "recording"
        for event in result["events"]
    )
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
