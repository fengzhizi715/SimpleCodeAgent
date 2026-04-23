"""Tests for V2 P1 persistence and replay."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from app.api.routes.debug import get_v2_run_replay, get_v2_session_replay
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
