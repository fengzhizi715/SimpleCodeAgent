"""Tests for V2 P0 capabilities."""

from __future__ import annotations

from pathlib import Path

from app.cli.entry import run_agent_task
from app.contracts.agent import AgentResult, AgentTask, SharedWorkspace
from app.contracts.message import ChatMessage
from app.contracts.run import RunChoice, RunRequest, RunResult
from app.db.sqlite import SQLiteDB
from app.llm.client import LLMProvider
from app.trace.recorder import JsonlTraceRecorder
from app.trace.repository import SQLiteTraceRepository
from app.v1.tools.registry import ToolRegistry
from app.v2.agents import PlannerAgent, TesterAgent
from app.v2.base import AgentContext, OrchestratorDelegationClient


class QueueProvider(LLMProvider):
    """Deterministic provider for V2 tests."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.requests: list[RunRequest] = []

    def chat(self, chat_request: RunRequest) -> RunResult:
        self.requests.append(chat_request)
        if not self._responses:  # pragma: no cover - defensive
            raise AssertionError("No fake responses left.")
        content = self._responses.pop(0)
        return RunResult(
            id="fake-response",
            model=chat_request.model,
            reasoning_mode=chat_request.reasoning_mode,
            choices=[
                RunChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=content),
                    finish_reason="stop",
                )
            ],
        )


def _make_context(tmp_path: Path, provider: LLMProvider) -> AgentContext:
    db = SQLiteDB(tmp_path / "v2-p0.sqlite3")
    return AgentContext(
        provider=provider,
        model="fake-model",
        reasoning_mode="default",
        tool_registry=ToolRegistry(workspace_root=tmp_path),
        trace_repository=SQLiteTraceRepository(db),
        trace_recorder=JsonlTraceRecorder(run_id="test-run", trace_dir=tmp_path / ".traces"),
        workspace_root=tmp_path,
        session_id="test-session",
        run_id="test-run",
    )


def test_planner_agent_prefers_llm_structured_plan(tmp_path: Path) -> None:
    provider = QueueProvider(
        [
            """
            {
              "summary": "llm plan",
              "steps": [
                {
                  "title": "分析项目结构",
                  "goal": "分析项目结构并找到关键文件",
                  "type": "analysis",
                  "description": "先理解项目结构",
                  "suggested_agent": "analyst",
                  "input_requirements": ["用户目标"],
                  "success_criteria": ["得到项目摘要"],
                  "max_retries": 1
                },
                {
                  "title": "修改实现",
                  "goal": "按计划完成代码修改",
                  "type": "coding",
                  "description": "执行局部代码改动",
                  "suggested_agent": "coder",
                  "input_requirements": ["项目摘要", "目标文件"],
                  "success_criteria": ["得到变更摘要"],
                  "max_retries": 1
                }
              ]
            }
            """
        ]
    )
    agent = PlannerAgent()
    workspace = SharedWorkspace(session_id="test-session", run_id="test-run", user_goal="做一个 v2 规划")
    task = AgentTask(
        session_id="test-session",
        run_id="test-run",
        goal="做一个 v2 规划",
        step_type="planning",
        target_agent="planner",
    )

    result = agent.run(
        task=task,
        workspace=workspace,
        context=_make_context(tmp_path, provider),
        prompt_context={},
    )

    plan = result.output_data["plan"]
    assert result.status == "completed"
    assert len(plan["steps"]) == 2
    assert plan["steps"][0]["suggested_agent"] == "analyst"
    assert plan["steps"][1]["tool_name"] == "write_file"
    assert provider.requests, "planner should call LLM provider"


def test_tester_agent_prefers_targeted_test_command(tmp_path: Path) -> None:
    provider = QueueProvider([])
    context = _make_context(tmp_path, provider)
    context.tool_registry.register_default_tools()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    tester = TesterAgent()
    workspace = SharedWorkspace(session_id="test-session", run_id="test-run", user_goal="验证改动")
    task = AgentTask(
        session_id="test-session",
        run_id="test-run",
        goal="运行测试",
        step_type="testing",
        target_agent="tester",
    )

    result = tester.run(
        task=task,
        workspace=workspace,
        context=context,
        prompt_context={
            "coder_context": {"modified_files": ["tests/test_sample.py"]},
            "analysis_context": {},
        },
    )

    assert result.status == "completed"
    assert result.output_data["selected_command"] == "pytest -q tests/test_sample.py"
    assert result.output_data["test_report"]["status"] == "passed"


def test_agent_context_excludes_delegation_interface(tmp_path: Path) -> None:
    context = _make_context(tmp_path, QueueProvider([]))
    assert not hasattr(context, "delegate_task")


def test_orchestrator_delegation_client_is_a_separate_capability(tmp_path: Path) -> None:
    context = _make_context(tmp_path, QueueProvider([]))
    workspace = SharedWorkspace(session_id="test-session", run_id="test-run", user_goal="demo")
    task = AgentTask(
        session_id="test-session",
        run_id="test-run",
        goal="让 coder 执行任务",
        step_type="coding",
        target_agent="coder",
    )
    called: dict[str, object] = {}

    def _delegate(**kwargs: object) -> AgentResult:
        called.update(kwargs)
        delegated_task = kwargs["task"]
        assert isinstance(delegated_task, AgentTask)
        return AgentResult(
            task_id=delegated_task.task_id,
            agent_id=str(kwargs["agent_id"]),
            status="completed",
            summary="delegated",
        )

    client = OrchestratorDelegationClient(_delegate)
    result = client.delegate(
        agent_id="coder",
        task=task,
        workspace=workspace,
        context=context,
        trace_events=[],
        delegation_records=[],
        delegation_start_event_ids={},
    )

    assert result.status == "completed"
    assert called["agent_id"] == "coder"
    assert called["workspace"] is workspace
    assert called["context"] is context


def test_cli_supports_v2_path(monkeypatch, tmp_path: Path) -> None:
    class FakeOpenAICompatibleProvider:
        def __init__(self, **_: object) -> None:
            pass

    class FakeRuntime:
        def run(self, **kwargs: object) -> RunResult:
            return RunResult(
                id="v2-cli-run",
                model="fake-model",
                reasoning_mode="default",
                choices=[RunChoice(index=0, message=ChatMessage(role="assistant", content="v2 cli works"))],
                run_id="v2-cli-run",
                session_id=str(kwargs["session_id"]),
                status="completed",
                final_output="v2 cli works",
            )

    monkeypatch.setattr("app.cli.entry.OpenAICompatibleProvider", FakeOpenAICompatibleProvider)
    monkeypatch.setattr("app.cli.entry.build_orchestrator_runtime", lambda trace_repo: FakeRuntime())

    result, version, session_id, trace_lines = run_agent_task(
        task="run v2 from cli",
        version="v2",
        model="fake-model",
        reasoning_mode="default",
        base_url="https://example.invalid",
        api_key="fake-key",
        service_token="",
        system_prompt="You are helpful.",
        temperature=0.0,
        session_id="v2-cli-session",
        workdir=str(tmp_path),
        max_steps=4,
        run_timeout_seconds=30,
        include_trace=False,
    )

    assert version == "v2"
    assert session_id.startswith("v2-cli-session@")
    assert result.final_output == "v2 cli works"
    assert trace_lines == []
