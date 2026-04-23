"""Tests for V2 P0 capabilities."""

from __future__ import annotations

from pathlib import Path

from app.cli.entry import run_agent_task
from app.contracts.agent import AgentResult, AgentTask, SharedWorkspace
from app.contracts.message import ChatMessage
from app.contracts.run import RunChoice, RunMetrics, RunRequest, RunResult, RunUsage
from app.db.sqlite import SQLiteDB
from app.llm.client import LLMProvider
from app.trace.recorder import JsonlTraceRecorder
from app.trace.repository import SQLiteTraceRepository
from app.v1.tools.registry import ToolRegistry
from app.v2.agents import AnalystAgent, CoderAgent, PlannerAgent, ReviewerAgent, TesterAgent
from app.v2.base import AgentContext, OrchestratorDelegationClient
from app.v2.agent_impls import describe_agent_matrix
from app.cli.entry import print_agent_matrix
from app.v2.factory import build_default_registry


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


class FakeCoderLoop:
    """Minimal stub loop for CoderAgent happy path tests."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root

    def run(self, **kwargs: object) -> RunResult:
        target = self.workspace_root / "app" / "sample.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("def hello() -> str:\n    return 'world'\n", encoding="utf-8")
        return RunResult(
            id="fake-coder-run",
            model=str(kwargs.get("model", "fake-model")),
            reasoning_mode=str(kwargs.get("reasoning_mode", "default")),
            choices=[
                RunChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content="已完成最小改动。"),
                    finish_reason="stop",
                )
            ],
            run_id="fake-coder-run",
            step_count=1,
            status="completed",
            final_output="已完成最小改动。",
            usage=RunUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            metrics=RunMetrics(llm_call_count=1, tool_call_count=2),
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
    assert result.metrics is not None
    assert result.metrics.llm_call_count == 1
    assert provider.requests, "planner should call LLM provider"


def test_planner_agent_routes_summary_steps_to_analyst(tmp_path: Path) -> None:
    provider = QueueProvider(
        [
            """
            {
              "summary": "analysis plan",
              "steps": [
                {
                  "title": "总结目录与模块组织",
                  "goal": "结合目录和关键文件内容，总结项目结构、模块职责和开发约定。",
                  "type": "general",
                  "description": "输出项目结构概述，不做代码修改",
                  "suggested_agent": "coder",
                  "input_requirements": ["目录结构", "关键文件"],
                  "success_criteria": ["给出结构化项目总结"],
                  "max_retries": 1
                }
              ]
            }
            """
        ]
    )
    agent = PlannerAgent()
    workspace = SharedWorkspace(session_id="test-session", run_id="test-run", user_goal="分析项目结构")
    task = AgentTask(
        session_id="test-session",
        run_id="test-run",
        goal="分析项目结构",
        step_type="planning",
        target_agent="planner",
    )

    result = agent.run(
        task=task,
        workspace=workspace,
        context=_make_context(tmp_path, provider),
        prompt_context={},
    )

    step = result.output_data["plan"]["steps"][0]
    assert step["type"] == "analysis"
    assert step["suggested_agent"] == "analyst"
    assert step["tool_name"] == "file_search"


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
    assert result.metrics is not None
    assert result.metrics.tool_call_count == 1


def test_analyst_agent_happy_path(tmp_path: Path) -> None:
    provider = QueueProvider([])
    context = _make_context(tmp_path, provider)
    context.tool_registry.register_default_tools()
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("def main() -> None:\n    pass\n", encoding="utf-8")
    agent = AnalystAgent()
    workspace = SharedWorkspace(session_id="test-session", run_id="test-run", user_goal="分析项目")
    task = AgentTask(
        session_id="test-session",
        run_id="test-run",
        goal="分析项目结构并给出摘要",
        step_type="analysis",
        target_agent="analyst",
    )

    result = agent.run(task=task, workspace=workspace, context=context, prompt_context={})

    assert result.status == "completed"
    assert result.output_data["project_summary"]
    assert isinstance(result.output_data["key_files"], list)
    assert "构建方式" in result.output_data["project_summary"]
    assert result.metrics is not None
    assert result.metrics.tool_call_count >= 2


def test_coder_agent_happy_path(tmp_path: Path) -> None:
    provider = QueueProvider([])
    context = _make_context(tmp_path, provider)
    agent = CoderAgent(agent_loop=FakeCoderLoop(tmp_path))
    workspace = SharedWorkspace(session_id="test-session", run_id="test-run", user_goal="实现小改动")
    task = AgentTask(
        session_id="test-session",
        run_id="test-run",
        goal="新增一个最小函数",
        step_type="coding",
        target_agent="coder",
        success_criteria=["生成可运行代码"],
    )

    result = agent.run(task=task, workspace=workspace, context=context, prompt_context={})

    assert result.status == "completed"
    assert "app/sample.py" in result.output_data["created_files"] or "app/sample.py" in result.output_data["modified_files"]
    assert result.usage is not None
    assert result.usage.total_tokens == 15
    assert result.metrics is not None
    assert result.metrics.tool_call_count == 2


def test_reviewer_agent_happy_path(tmp_path: Path) -> None:
    provider = QueueProvider([])
    context = _make_context(tmp_path, provider)
    context.tool_registry.register_default_tools()
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "sample.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    agent = ReviewerAgent()
    workspace = SharedWorkspace(
        session_id="test-session",
        run_id="test-run",
        user_goal="review 本次改动",
        latest_patch_summary="已修改 app/sample.py，新增 add 函数。",
    )
    task = AgentTask(
        session_id="test-session",
        run_id="test-run",
        goal="review patch",
        step_type="review",
        target_agent="reviewer",
    )
    prompt_context = {
        "coder_context": {"modified_files": ["app/sample.py"], "diff_previews": {"app/sample.py": "+def add(a, b):"}},
        "analysis_context": {"key_files": [{"path": "app/sample.py", "reason": "core logic"}]},
        "project_summary": "simple project",
    }

    result = agent.run(task=task, workspace=workspace, context=context, prompt_context=prompt_context)

    assert result.status == "completed"
    assert "review_summary" in result.output_data
    assert isinstance(result.output_data["issues"], list)


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


def test_build_default_registry_supports_reviewer_toggle() -> None:
    with_reviewer = build_default_registry(enable_reviewer=True)
    without_reviewer = build_default_registry(enable_reviewer=False)

    assert with_reviewer.get("reviewer") is not None
    assert without_reviewer.get("reviewer") is None


def test_describe_agent_matrix_contains_core_roles() -> None:
    matrix = describe_agent_matrix()
    roles = {item["role"] for item in matrix}
    assert {"planner", "analyst", "coder", "tester", "reviewer"}.issubset(roles)
    assert all(isinstance(item["capabilities"], list) for item in matrix)


def test_print_agent_matrix_outputs_roles(capsys) -> None:
    print_agent_matrix()
    output = capsys.readouterr().out
    assert "Agent Matrix:" in output
    assert "planner" in output
    assert "coder" in output


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
