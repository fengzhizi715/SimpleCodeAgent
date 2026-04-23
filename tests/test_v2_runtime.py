"""V2 Orchestrator Runtime tests."""

from __future__ import annotations

from pathlib import Path

from app.contracts.agent import AgentResult, AgentSpec, AgentTask, SharedWorkspace, TestReport
from app.contracts.planner import Plan, PlanStep
from app.contracts.run import RunMetrics, RunRequest, RunResult, RunUsage
from app.db.sqlite import SQLiteDB
from app.llm.client import LLMProvider
from app.trace.repository import SQLiteTraceRepository
from app.v1.tools.registry import ToolRegistry
from app.v2.base import AgentBase, AgentContext
from app.v2.registry import AgentRegistry
from app.v2.runtime import OrchestratorRuntime


class DummyProvider(LLMProvider):
    """测试中的占位 Provider。"""

    def chat(self, chat_request: RunRequest) -> RunResult:  # pragma: no cover - should not be called
        raise AssertionError("DummyProvider.chat should not be called in this test.")


class FakePlannerAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            AgentSpec(
                agent_id="planner",
                role="planner",
                description="fake planner",
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
            summary="fake plan",
            steps=[
                PlanStep(
                    title="分析项目",
                    goal="分析项目",
                    type="analysis",
                    suggested_agent="analyst",
                    success_criteria=["产出项目摘要"],
                ),
                PlanStep(
                    title="修改代码",
                    goal="修改代码",
                    type="coding",
                    suggested_agent="coder",
                    success_criteria=["产出改动摘要"],
                ),
                PlanStep(
                    title="运行测试",
                    goal="运行测试",
                    type="testing",
                    suggested_agent="tester",
                    success_criteria=["测试通过"],
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


class FakeAnalystAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            AgentSpec(
                agent_id="analyst",
                role="analyst",
                description="fake analyst",
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
            usage=RunUsage(prompt_tokens=11, completion_tokens=7, total_tokens=18),
            metrics=RunMetrics(llm_call_count=1, tool_call_count=3),
            output_data={
                "project_summary": "这是一个带 v1/v2 目录的示例工程。",
                "module_responsibilities": {"app": "主体代码目录。", "tests": "测试目录。"},
                "entry_files": ["app/main.py", "app/api/routes/agent.py"],
                "key_files": [{"path": "app/main.py", "reason": "应用入口"}],
                "coding_hints": ["优先从 app 和 tests 理解结构。"],
            },
        )


class FakeCoderAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            AgentSpec(
                agent_id="coder",
                role="coder",
                description="fake coder",
                capabilities=["coding"],
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
            agent_id="coder",
            status="completed",
            summary="已修改 app/v2 相关代码。",
            usage=RunUsage(prompt_tokens=20, completion_tokens=9, total_tokens=29),
            metrics=RunMetrics(llm_call_count=1, tool_call_count=2),
            output_data={"final_output": "patched"},
        )


class FailingFakeCoderAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            AgentSpec(
                agent_id="coder",
                role="coder",
                description="failing fake coder",
                capabilities=["coding"],
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
            agent_id="coder",
            status="failed",
            summary="编码失败",
            error_message="无法生成可靠改动",
        )


class TwoStepPlannerAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            AgentSpec(
                agent_id="planner",
                role="planner",
                description="two-step planner",
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
            summary="two-step plan",
            steps=[
                PlanStep(
                    title="分析",
                    goal="先分析",
                    type="analysis",
                    suggested_agent="analyst",
                    success_criteria=["有摘要"],
                ),
                PlanStep(
                    title="编码",
                    goal="再编码",
                    type="coding",
                    suggested_agent="coder",
                    success_criteria=["有改动"],
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


class FakeTesterAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            AgentSpec(
                agent_id="tester",
                role="tester",
                description="fake tester",
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
            executed_command="pytest -q",
            summary="测试通过。",
        )
        return AgentResult(
            task_id=task.task_id,
            agent_id="tester",
            status="completed",
            summary="测试通过。",
            metrics=RunMetrics(tool_call_count=1),
            output_data={"test_report": report.model_dump()},
        )


def test_v2_runtime_orchestrates_agents_and_updates_workspace(tmp_path: Path) -> None:
    db = SQLiteDB(tmp_path / "trace.sqlite3")
    trace_repository = SQLiteTraceRepository(db)
    registry = AgentRegistry()
    registry.register(FakePlannerAgent())
    registry.register(FakeAnalystAgent())
    registry.register(FakeCoderAgent())
    registry.register(FakeTesterAgent())
    runtime = OrchestratorRuntime(registry=registry, trace_repository=trace_repository)

    result = runtime.run(
        provider=DummyProvider(),
        model="dummy-model",
        task="为 v2 落一个多智能体骨架",
        session_id="test-session",
        tool_registry=ToolRegistry(workspace_root=tmp_path),
        workspace_root=tmp_path,
        max_steps=6,
    )

    assert result.status == "completed"
    assert result.step_count == 3
    assert "项目分析：这是一个带 v1/v2 目录的示例工程。" in result.final_output
    assert "模块职责：app: 主体代码目录。；tests: 测试目录。" in result.final_output
    assert "关键文件：app/main.py(应用入口)" in result.final_output
    assert "开发提示：优先从 app 和 tests 理解结构。" in result.final_output
    assert "代码改动：已修改 app/v2 相关代码。" in result.final_output
    assert "测试结果：passed，测试通过。" in result.final_output
    assert result.usage is not None
    assert result.usage.total_tokens == 47
    assert result.metrics is not None
    assert result.metrics.llm_call_count == 2
    assert result.metrics.tool_call_count == 6
    assert any(event.event_type == "delegation_started" for event in result.trace)
    assert any(event.event_type == "agent_selected" for event in result.trace)


def test_v2_runtime_fails_fast_when_coder_fails(tmp_path: Path) -> None:
    db = SQLiteDB(tmp_path / "trace-fail.sqlite3")
    trace_repository = SQLiteTraceRepository(db)
    registry = AgentRegistry()
    registry.register(TwoStepPlannerAgent())
    registry.register(FakeAnalystAgent())
    registry.register(FailingFakeCoderAgent())
    runtime = OrchestratorRuntime(registry=registry, trace_repository=trace_repository)

    result = runtime.run(
        provider=DummyProvider(),
        model="dummy-model",
        task="验证失败路径",
        session_id="test-session",
        tool_registry=ToolRegistry(workspace_root=tmp_path),
        workspace_root=tmp_path,
        max_steps=6,
        max_replans=0,
    )

    assert result.status == "failed"
    assert "无法生成可靠改动" in (result.final_output or "")
    assert any(event.event_type == "run_failed" for event in (result.trace or []))
