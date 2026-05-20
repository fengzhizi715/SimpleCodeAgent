"""Tests for V2 P1 persistence and replay."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException

from app.api.routes.debug import get_run_detail, get_v2_run_replay, get_v2_session_replay
from app.contracts.agent import AgentResult, AgentSpec, AgentTask, SharedWorkspace, TestReport
from app.contracts.planner import Plan, PlanStep
from app.contracts.run import RunRequest, RunResult
from app.contracts.trace import TraceEvent
from app.db.sqlite import SQLiteDB
from app.llm.client import LLMProvider
from app.trace.repository import SQLiteTraceRepository
from app.v1.tools.registry import ToolRegistry
from app.v2.base import AgentBase, AgentContext
from app.v2.registry import AgentRegistry
from app.v2.repository import V2Repository
from app.v2.runtime import OrchestratorRuntime
from app.v2.viewer import format_delegation_tree, format_execution_log


class DummyProvider(LLMProvider):
    def chat(self, chat_request: RunRequest) -> RunResult:  # pragma: no cover - should not be called
        raise AssertionError("DummyProvider.chat should not be called in this test.")


class ReplayPlannerAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            AgentSpec(
                agent_id="planner",
                role="planner",
                description="replay planner",
                capabilities=["plan"],
            )
        )

    def run(
        self,
        *,
        task: AgentTask,
        workspace: SharedWorkspace,
        context: AgentContext,
        prompt_context: dict[str, object],
    ) -> AgentResult:
        plan = Plan(
            summary="replay plan",
            steps=[
                PlanStep(
                    title="分析项目",
                    goal="分析项目",
                    type="analysis",
                    suggested_agent="analyst",
                    success_criteria=["产出项目摘要"],
                ),
                PlanStep(
                    title="运行测试",
                    goal="运行测试",
                    type="testing",
                    suggested_agent="tester",
                    success_criteria=["得到测试报告"],
                ),
            ],
        )
        return AgentResult(
            task_id=task.task_id,
            agent_id="planner",
            status="completed",
            summary="planned",
            output_data={"plan": plan.model_dump()},
        )


class ReplayAnalystAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            AgentSpec(
                agent_id="analyst",
                role="analyst",
                description="replay analyst",
                capabilities=["analysis"],
            )
        )

    def run(
        self,
        *,
        task: AgentTask,
        workspace: SharedWorkspace,
        context: AgentContext,
        prompt_context: dict[str, object],
    ) -> AgentResult:
        return AgentResult(
            task_id=task.task_id,
            agent_id="analyst",
            status="completed",
            summary="分析完成",
            output_data={
                "project_summary": "项目包含 app/v1、app/v2 和 tests。",
                "entry_files": ["app/main.py", "app/api/routes/agent.py"],
                "key_files": [{"path": "app/v2/runtime.py", "reason": "主执行链路"}],
            },
        )


class ReplayTesterAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            AgentSpec(
                agent_id="tester",
                role="tester",
                description="replay tester",
                capabilities=["testing"],
            )
        )

    def run(
        self,
        *,
        task: AgentTask,
        workspace: SharedWorkspace,
        context: AgentContext,
        prompt_context: dict[str, object],
    ) -> AgentResult:
        report = TestReport(
            status="passed",
            executed_command="pytest -q tests/test_v2_runtime.py",
            summary="测试通过。",
        )
        return AgentResult(
            task_id=task.task_id,
            agent_id="tester",
            status="completed",
            summary="测试通过。",
            output_data={"test_report": report.model_dump()},
        )


def test_trace_repository_persists_structured_fields(tmp_path: Path) -> None:
    db = SQLiteDB(tmp_path / "trace.sqlite3")
    repository = SQLiteTraceRepository(db)
    event = TraceEvent(
        run_id="run-1",
        root_run_id="root-1",
        parent_run_id="parent-run",
        session_id="session-1",
        actor="tester",
        action="testing",
        status="completed",
        input_summary="run pytest",
        output_summary="passed",
        parent_event_id="evt-parent",
        started_at="2025-01-01T00:00:00+00:00",
        ended_at="2025-01-01T00:00:05+00:00",
        event_type="delegation_finished",
        message="tester finished",
        payload={"k": "v"},
    )

    repository.save_event("run-1", event)
    loaded = repository.query_timeline("run-1")

    assert len(loaded) == 1
    assert loaded[0].actor == "tester"
    assert loaded[0].action == "testing"
    assert loaded[0].status == "completed"
    assert loaded[0].input_summary == "run pytest"
    assert loaded[0].output_summary == "passed"
    assert loaded[0].parent_event_id == "evt-parent"
    assert loaded[0].payload == {"k": "v"}


def test_v2_runtime_persists_workspace_delegations_and_replay(tmp_path: Path) -> None:
    db = SQLiteDB(tmp_path / "v2.sqlite3")
    trace_repository = SQLiteTraceRepository(db)
    v2_repository = V2Repository(db)
    registry = AgentRegistry()
    registry.register(ReplayPlannerAgent())
    registry.register(ReplayAnalystAgent())
    registry.register(ReplayTesterAgent())
    runtime = OrchestratorRuntime(
        registry=registry,
        trace_repository=trace_repository,
        v2_repository=v2_repository,
    )

    result = runtime.run(
        provider=DummyProvider(),
        model="dummy-model",
        task="做一次可回放的 v2 执行",
        session_id="replay-session",
        tool_registry=ToolRegistry(workspace_root=tmp_path),
        workspace_root=tmp_path,
        max_steps=5,
    )

    stored_workspace = v2_repository.get_workspace(result.run_id or "")
    delegations = v2_repository.list_delegations_for_run(result.run_id or "")
    run_replay = runtime.get_run_replay(result.run_id or "")
    session_replay = runtime.get_session_replay("replay-session")
    delegation_started_events = [
        item for item in run_replay["trace"] if item["event_type"] == "delegation_started"
    ]
    delegation_finished_events = [
        item for item in run_replay["trace"] if item["event_type"] == "delegation_finished"
    ]
    run_finished_events = [item for item in run_replay["trace"] if item["event_type"] == "run_finished"]

    assert result.status == "completed"
    assert stored_workspace is not None
    assert stored_workspace.project_summary == "项目包含 app/v1、app/v2 和 tests。"
    assert stored_workspace.latest_test_result is not None
    assert stored_workspace.latest_test_result.executed_command == "pytest -q tests/test_v2_runtime.py"
    assert len(delegations) == 3
    assert run_replay["run"]["run_id"] == result.run_id
    assert run_replay["workspace"]["project_summary"] == "项目包含 app/v1、app/v2 和 tests。"
    assert len(run_replay["delegations"]) == 3
    assert any(item["event_type"] == "delegation_started" for item in run_replay["trace"])
    assert delegation_started_events
    assert all(item.get("started_at") for item in delegation_started_events)
    assert all(item.get("ended_at") for item in delegation_started_events)
    assert delegation_finished_events
    assert all(item.get("parent_event_id") for item in delegation_finished_events)
    assert run_finished_events
    assert all(item.get("parent_event_id") for item in run_finished_events)
    assert session_replay["session_id"] == "replay-session"
    assert len(session_replay["runs"]) == 1
    assert len(session_replay["workspaces"]) == 1
    assert len(session_replay["delegations"]) == 3
    assert any(item["event_type"] == "run_finished" for item in session_replay["trace"])
    assert run_replay["execution_log"]
    assert run_replay["delegation_tree"]
    assert "最终结论" in " ".join(run_replay["teaching_view"]["key_takeaways"])


def test_debug_routes_and_viewers_expose_replay(monkeypatch) -> None:
    replay = {
        "run": {"run_id": "run-1", "status": "completed", "step_count": 2, "final_output": "done"},
        "workspace": {"project_summary": "summary", "latest_patch_summary": "patch"},
        "delegations": [
            {
                "delegation_id": "d1",
                "step_id": "s1",
                "parent_agent_id": "orchestrator",
                "target_agent": "analyst",
                "task_id": "t1",
                "status": "completed",
                "summary": "analysis done",
            }
        ],
        "trace": [
            {
                "event_type": "delegation_started",
                "created_at": "2025-01-01T00:00:00+00:00",
                "actor": "orchestrator",
                "status": "started",
                "message": "Delegating",
                "payload": {"task_id": "t1", "step_id": "s1", "target_agent": "analyst"},
            }
        ],
        "execution_log": [
            {
                "sequence": 1,
                "event_type": "delegation_started",
                "actor": "orchestrator",
                "status": "started",
                "message": "Delegating",
            }
        ],
        "delegation_tree": [
            {
                "step_id": "s1",
                "children": [
                    {
                        "parent_agent_id": "orchestrator",
                        "target_agent": "analyst",
                        "status": "completed",
                        "summary": "analysis done",
                    }
                ],
            }
        ],
        "teaching_view": {"key_takeaways": ["最终结论：done"]},
    }

    class FakeRuntime:
        def get_run_replay(self, run_id: str) -> dict[str, object]:
            return replay if run_id == "run-1" else {}

        def get_session_replay(self, session_id: str) -> dict[str, object]:
            return {
                "session_id": session_id,
                "runs": [replay["run"]],
                "workspaces": [replay["workspace"]],
                "delegations": replay["delegations"],
                "trace": replay["trace"],
                "execution_log": replay["execution_log"],
                "delegation_tree": replay["delegation_tree"],
                "teaching_view": replay["teaching_view"],
            }

    monkeypatch.setattr("app.api.routes.debug.get_v2_runtime", lambda: FakeRuntime())

    run_response = get_v2_run_replay("run-1")
    session_response = get_v2_session_replay("session-1")

    assert run_response.run["run_id"] == "run-1"
    assert session_response.session_id == "session-1"
    assert "delegation_started" in format_execution_log(run_response.execution_log)
    assert "orchestrator -> analyst" in format_delegation_tree(run_response.delegation_tree)

    try:
        get_v2_run_replay("missing")
    except HTTPException as exc:
        assert exc.status_code == 404
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected HTTPException for missing replay.")


def test_generic_run_detail_routes_v2_replay(monkeypatch) -> None:
    replay = {
        "run": {"run_id": "run-1", "status": "completed", "step_count": 2, "final_output": "done"},
        "workspace": {"project_summary": "summary"},
        "delegations": [],
        "artifacts": [],
        "trace": [],
        "execution_log": [],
        "delegation_tree": [],
        "execution_nodes": [],
        "teaching_view": {},
    }

    class FakeDB:
        def fetchone(self, _sql: str, _params: tuple[str, ...]) -> dict[str, object]:
            return {
                "run_id": "run-1",
                "session_id": "session-1",
                "model": "fake-model",
                "task": "task",
                "workdir": ".",
                "status": "completed",
                "step_count": 2,
                "final_output": "done",
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:01+00:00",
                "agent_version": "v2",
            }

    class FakeRuntime:
        def get_run_replay(self, run_id: str) -> dict[str, object]:
            return replay if run_id == "run-1" else {}

    monkeypatch.setattr("app.api.routes.debug.SQLiteDB", lambda: FakeDB())
    monkeypatch.setattr("app.api.routes.debug.get_v2_runtime", lambda: FakeRuntime())

    response = get_run_detail("run-1")

    assert response.version == "v2"
    assert response.run["run_id"] == "run-1"


def test_generic_run_detail_routes_v3_report(monkeypatch) -> None:
    graph_finished = TraceEvent(
        run_id="run-v3",
        event_type="graph_finished",
        message="v3 done",
        payload={
            "run_id": "run-v3",
            "graph_id": "graph-v3",
            "status": "completed",
            "shared_state": {
                "planning": {
                    "goal_kind": "testing",
                    "template_name": "default",
                    "recovery_strategy": "fix_and_retest",
                }
            },
            "execution_nodes": [{"node_id": "test_runner", "kind": "graph", "skill_name": "test_runner", "status": "done"}],
            "trigger_diagnostics": [{"trigger_rule_id": "rule-1", "source_event_type": "test_failed", "target_skill_name": "coding", "status": "executed"}],
        },
    )

    class FakeDB:
        def fetchone(self, _sql: str, _params: tuple[str, ...]) -> dict[str, object]:
            return {
                "run_id": "run-v3",
                "session_id": "session-v3",
                "model": "",
                "task": "run tests",
                "workdir": ".",
                "status": "completed",
                "step_count": 2,
                "final_output": "{}",
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:01+00:00",
                "agent_version": "v3",
            }

    class FakeTraceRepository:
        def query_timeline(self, run_id: str) -> list[TraceEvent]:
            return [graph_finished] if run_id == "run-v3" else []

    monkeypatch.setattr("app.api.routes.debug.SQLiteDB", lambda: FakeDB())
    monkeypatch.setattr("app.api.routes.debug.get_trace_repository", lambda: FakeTraceRepository())

    response = get_run_detail("run-v3")

    assert response.version == "v3"
    assert response.report is not None
    assert response.planning["goal_kind"] == "testing"
    assert response.execution_nodes[0]["node_id"] == "test_runner"


def test_generic_run_detail_restores_v3_report_from_final_output_when_trace_payload_is_thin(monkeypatch) -> None:
    graph_finished = TraceEvent(
        run_id="run-v3",
        event_type="graph_finished",
        message="v3 done",
        payload={
            "event_id": "evt-graph-finished",
            "run_id": "run-v3",
            "event_type": "graph_finished",
            "source": "execution_kernel",
            "payload": {
                "run_id": "run-v3",
                "graph_id": "graph-v3",
                "status": "completed",
            },
            "execution_chain_id": None,
        },
    )

    full_report = {
        "run_id": "run-v3",
        "graph_id": "graph-v3",
        "status": "completed",
        "completed_node_ids": ["analyze_repo", "coding", "test_runner"],
        "failed_node_ids": [],
        "recovered_node_ids": [],
        "skipped_node_ids": [],
        "node_outputs": {
            "analyze_repo": {"repo_profile": "gradle_kotlin"},
            "coding": {"summary": "fixed login bug"},
            "test_runner": {"summary": "Tests passed: ./gradlew test", "exit_code": 0},
        },
        "shared_state": {
            "planning": {
                "goal_kind": "coding",
                "template_name": "repo_fix",
                "planning_mode": "llm",
                "execution_layers": [["analyze_repo"], ["coding"], ["test_runner"]],
            }
        },
        "execution_nodes": [
            {"node_id": "analyze_repo", "kind": "graph", "skill_name": "analyze_repo", "status": "completed"},
            {"node_id": "coding", "kind": "graph", "skill_name": "coding", "status": "completed"},
            {"node_id": "test_runner", "kind": "graph", "skill_name": "test_runner", "status": "completed"},
        ],
        "trigger_diagnostics": [],
        "agent_messages": [],
    }

    class FakeDB:
        def fetchone(self, _sql: str, _params: tuple[str, ...]) -> dict[str, object]:
            return {
                "run_id": "run-v3",
                "session_id": "session-v3",
                "model": "fake-model",
                "task": "fix login",
                "workdir": ".",
                "status": "completed",
                "step_count": 3,
                "final_output": json.dumps(full_report),
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:01+00:00",
                "agent_version": "v3",
            }

    class FakeTraceRepository:
        def query_timeline(self, run_id: str) -> list[TraceEvent]:
            return [graph_finished] if run_id == "run-v3" else []

    monkeypatch.setattr("app.api.routes.debug.SQLiteDB", lambda: FakeDB())
    monkeypatch.setattr("app.api.routes.debug.get_trace_repository", lambda: FakeTraceRepository())

    response = get_run_detail("run-v3")

    assert response.version == "v3"
    assert response.report is not None
    assert response.report["graph_id"] == "graph-v3"
    assert response.planning["goal_kind"] == "coding"
    assert response.planning["planning_mode"] == "llm"
    assert [node["node_id"] for node in response.execution_nodes] == ["analyze_repo", "coding", "test_runner"]
    assert response.report["node_outputs"]["test_runner"]["exit_code"] == 0


def test_generic_run_detail_builds_v3_runtime_summary(monkeypatch) -> None:
    graph_finished = TraceEvent(
        run_id="run-v3",
        event_type="graph_finished",
        message="v3 done",
        payload={
            "event_id": "evt-graph-finished",
            "run_id": "run-v3",
            "event_type": "graph_finished",
            "source": "execution_kernel",
            "payload": {
                "run_id": "run-v3",
                "graph_id": "graph-v3",
                "status": "completed",
                "shared_state": {
                    "planning": {
                        "goal_kind": "testing",
                        "template_name": "fix_and_retest",
                        "planning_mode": "llm",
                    }
                },
                "execution_nodes": [
                    {"node_id": "test_runner", "kind": "graph", "skill_name": "test_runner", "status": "failed"},
                    {"node_id": "trigger:fix-tests:evt-1", "kind": "trigger", "skill_name": "coding", "status": "done"},
                    {"node_id": "autonomy:req-1", "kind": "trigger", "skill_name": "test_runner", "status": "done"},
                ],
                "trigger_diagnostics": [
                    {
                        "trigger_rule_id": "fix-tests",
                        "source_event_type": "test_failed",
                        "target_skill_name": "coding",
                        "status": "executed",
                        "details": {"cooldown_seconds": 30.0, "priority": 5},
                    },
                    {
                        "trigger_rule_id": "verify-code-updates",
                        "source_event_type": "code_updated",
                        "target_skill_name": "test_runner",
                        "status": "skipped",
                        "skip_reason": "cooldown",
                        "details": {
                            "skip_reason": "cooldown",
                            "cooldown_seconds": 60.0,
                            "cooldown_key": "verify-code-updates:app.py",
                        },
                    },
                ],
            },
            "metadata": {},
        },
    )
    trigger_skipped = TraceEvent(
        run_id="run-v3",
        event_type="trigger_skipped",
        message="trigger skipped",
        payload={
            "event_id": "evt-trigger-skipped",
            "run_id": "run-v3",
            "event_type": "trigger_skipped",
            "source": "test_runner",
            "payload": {
                "trigger_rule_id": "verify-code-updates",
                "source_event_type": "code_updated",
                "skip_reason": "cooldown",
                "cooldown_key": "verify-code-updates:app.py",
            },
            "metadata": {
                "governance_decision": {
                    "skip_reason": "cooldown",
                    "cooldown_seconds": 60.0,
                }
            },
        },
    )

    class FakeDB:
        def fetchone(self, _sql: str, _params: tuple[str, ...]) -> dict[str, object]:
            return {
                "run_id": "run-v3",
                "session_id": "session-v3",
                "model": "fake-model",
                "task": "run tests and recover",
                "workdir": ".",
                "status": "completed",
                "step_count": 3,
                "final_output": "{}",
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:01+00:00",
                "agent_version": "v3",
            }

    class FakeTraceRepository:
        def query_timeline(self, run_id: str) -> list[TraceEvent]:
            return [trigger_skipped, graph_finished] if run_id == "run-v3" else []

    monkeypatch.setattr("app.api.routes.debug.SQLiteDB", lambda: FakeDB())
    monkeypatch.setattr("app.api.routes.debug.get_trace_repository", lambda: FakeTraceRepository())

    response = get_run_detail("run-v3")

    assert response.runtime_summary is not None
    assert response.runtime_summary["run_mode"]["id"] == "graph_governance_intercept"
    assert response.runtime_summary["run_mode"]["label"] == "Graph + Governance Intercept"
    assert response.runtime_summary["governance_summary"]["status_counts"]["blocked"] == 1
    assert response.runtime_summary["governance_summary"]["status_counts"]["allowed"] == 1
    assert response.runtime_summary["flow_cards"][0]["event_type"] == "test_failed"
    assert response.runtime_summary["flow_cards"][0]["trigger_rule_id"] == "fix-tests"
    assert response.runtime_summary["flow_cards"][0]["follow_up_label"] == "coding"
    assert response.runtime_summary["flow_cards"][1]["governance_label"] == "Cooled Down"
    assert response.runtime_summary["demo_scenarios"] == [
        "测试失败 -> 自动补救 -> 再测",
        "代码变更 -> 自动 follow-up test",
        "事件命中但被 governance 拦截",
    ]


def test_generic_run_detail_infers_runtime_mode_from_trace_when_report_is_thin(monkeypatch) -> None:
    graph_finished = TraceEvent(
        run_id="run-v3-thin",
        event_type="graph_finished",
        message="v3 done",
        payload={
            "event_id": "evt-graph-finished",
            "run_id": "run-v3-thin",
            "event_type": "graph_finished",
            "source": "execution_kernel",
            "payload": {
                "run_id": "run-v3-thin",
                "graph_id": "graph-v3-thin",
                "status": "completed",
                "shared_state": {
                    "planning": {
                        "goal_kind": "testing",
                        "template_name": "default",
                    }
                },
                "execution_nodes": [
                    {"node_id": "test_runner", "kind": "graph", "skill_name": "test_runner", "status": "failed"},
                ],
                "trigger_diagnostics": [],
            },
        },
    )
    trigger_skipped = TraceEvent(
        run_id="run-v3-thin",
        event_type="trigger_skipped",
        message="trigger skipped",
        payload={
            "event_id": "evt-trigger-skipped",
            "run_id": "run-v3-thin",
            "event_type": "trigger_skipped",
            "source": "test_runner",
            "parent_event_id": "evt-test-failed",
            "trigger_rule_id": "trigger-test-failed",
            "payload": {
                "trigger_rule_id": "trigger-test-failed",
                "source_event_type": "test_failed",
                "skip_reason": "cooldown",
            },
            "metadata": {
                "governance_decision": {
                    "skip_reason": "cooldown",
                    "cooldown_seconds": 30.0,
                }
            },
        },
    )

    class FakeDB:
        def fetchone(self, _sql: str, _params: tuple[str, ...]) -> dict[str, object]:
            return {
                "run_id": "run-v3-thin",
                "session_id": "session-v3",
                "model": "fake-model",
                "task": "run tests",
                "workdir": ".",
                "status": "partial_completed",
                "step_count": 1,
                "final_output": "{}",
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:01+00:00",
                "agent_version": "v3",
            }

    class FakeTraceRepository:
        def query_timeline(self, run_id: str) -> list[TraceEvent]:
            return [trigger_skipped, graph_finished] if run_id == "run-v3-thin" else []

    monkeypatch.setattr("app.api.routes.debug.SQLiteDB", lambda: FakeDB())
    monkeypatch.setattr("app.api.routes.debug.get_trace_repository", lambda: FakeTraceRepository())

    response = get_run_detail("run-v3-thin")

    assert response.runtime_summary is not None
    assert response.runtime_summary["run_mode"]["id"] == "graph_governance_intercept"
    assert response.runtime_summary["flow_cards"][0]["event_type"] == "test_failed"
    assert response.runtime_summary["flow_cards"][0]["trigger_rule_id"] == "trigger-test-failed"
    assert response.runtime_summary["governance_summary"]["items"][0]["label"] == "Cooled Down"


def test_generic_run_detail_does_not_guess_demo_scenarios_without_runtime_follow_up(monkeypatch) -> None:
    graph_finished = TraceEvent(
        run_id="run-v3-plain",
        event_type="graph_finished",
        message="v3 done",
        payload={
            "run_id": "run-v3-plain",
            "graph_id": "graph-v3-plain",
            "status": "partial_completed",
            "shared_state": {
                "planning": {
                    "goal_kind": "testing",
                    "template_name": "default",
                }
            },
            "execution_nodes": [
                {"node_id": "test_runner", "kind": "graph", "skill_name": "test_runner", "status": "failed"},
            ],
            "trigger_diagnostics": [],
        },
    )

    class FakeDB:
        def fetchone(self, _sql: str, _params: tuple[str, ...]) -> dict[str, object]:
            return {
                "run_id": "run-v3-plain",
                "session_id": "session-v3",
                "model": "fake-model",
                "task": "run tests",
                "workdir": ".",
                "status": "partial_completed",
                "step_count": 1,
                "final_output": "{}",
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:01+00:00",
                "agent_version": "v3",
            }

    class FakeTraceRepository:
        def query_timeline(self, run_id: str) -> list[TraceEvent]:
            return [graph_finished] if run_id == "run-v3-plain" else []

    monkeypatch.setattr("app.api.routes.debug.SQLiteDB", lambda: FakeDB())
    monkeypatch.setattr("app.api.routes.debug.get_trace_repository", lambda: FakeTraceRepository())

    response = get_run_detail("run-v3-plain")

    assert response.runtime_summary is not None
    assert response.runtime_summary["run_mode"]["id"] == "graph_only"
    assert response.runtime_summary["demo_scenarios"] == []
