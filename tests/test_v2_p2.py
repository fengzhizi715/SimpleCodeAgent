"""Tests for V2 P2 enhancements."""

from __future__ import annotations

from pathlib import Path

from app.contracts.agent import AgentArtifact, AgentResult, AgentSpec, AgentTask, SharedWorkspace, TestReport
from app.contracts.message import ChatMessage
from app.contracts.planner import Plan, PlanStep
from app.contracts.run import RunChoice, RunRequest, RunResult
from app.db.sqlite import SQLiteDB
from app.llm.client import LLMProvider
from app.trace.recorder import JsonlTraceRecorder
from app.trace.repository import SQLiteTraceRepository
from app.v1.tools.read_file import ReadFileTool
from app.v1.tools.registry import ToolRegistry
from app.v2.agents import ReviewerAgent
from app.v2.base import AgentBase, AgentContext
from app.v2.registry import AgentRegistry
from app.v2.repository import V2Repository
from app.v2.runtime import OrchestratorRuntime
from app.v2.viewer import format_execution_nodes


class DummyProvider(LLMProvider):
    def chat(self, chat_request: RunRequest) -> RunResult:  # pragma: no cover - should not be called
        raise AssertionError("DummyProvider.chat should not be called in this test.")


class QueueProvider(LLMProvider):
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)

    def chat(self, chat_request: RunRequest) -> RunResult:
        content = self.responses.pop(0)
        return RunResult(
            id="review-response",
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


class P2PlannerAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(AgentSpec(agent_id="planner", role="planner", description="planner"))

    def run(
        self,
        *,
        task: AgentTask,
        workspace: SharedWorkspace,
        context: AgentContext,
        prompt_context: dict[str, object],
    ) -> AgentResult:
        plan = Plan(
            summary="p2 plan",
            steps=[
                PlanStep(
                    title="修改代码",
                    goal="修改代码",
                    type="coding",
                    suggested_agent="coder",
                    success_criteria=["产出 patch"],
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


class P2CoderAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(AgentSpec(agent_id="coder", role="coder", description="coder"))

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
            summary="已修改 app/v2/runtime.py。",
            output_data={
                "modified_files": ["app/v2/runtime.py"],
                "created_files": [],
                "deleted_files": [],
                "risk_notes": [],
            },
        )


class P2ReviewerAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(AgentSpec(agent_id="reviewer", role="reviewer", description="reviewer"))

    def run(
        self,
        *,
        task: AgentTask,
        workspace: SharedWorkspace,
        context: AgentContext,
        prompt_context: dict[str, object],
    ) -> AgentResult:
        output_data = {
            "review_summary": "发现 1 个中风险问题。",
            "issues": [
                {
                    "severity": "medium",
                    "title": "需要补测试覆盖",
                    "detail": "本次改动修改了 runtime 但没有对应的新回归用例。",
                    "file_path": "app/v2/runtime.py",
                }
            ],
            "recommended_action": "先补测试，再继续推进。",
        }
        return AgentResult(
            task_id=task.task_id,
            agent_id="reviewer",
            status="completed",
            summary="Review 发现 1 个需要关注的问题。",
            output_data=output_data,
            artifacts=[
                AgentArtifact(
                    key="review_report",
                    type="review",
                    summary="Review 发现 1 个需要关注的问题。",
                    producer_agent="reviewer",
                    content=output_data,
                )
            ],
        )


class P2TesterAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(AgentSpec(agent_id="tester", role="tester", description="tester"))

    def run(
        self,
        *,
        task: AgentTask,
        workspace: SharedWorkspace,
        context: AgentContext,
        prompt_context: dict[str, object],
    ) -> AgentResult:
        report = TestReport(status="passed", executed_command="pytest -q", summary="测试通过。")
        return AgentResult(
            task_id=task.task_id,
            agent_id="tester",
            status="completed",
            summary="测试通过。",
            output_data={"test_report": report.model_dump()},
        )


def test_v2_p2_reviewer_artifacts_and_execution_nodes(tmp_path: Path) -> None:
    db = SQLiteDB(tmp_path / "p2.sqlite3")
    trace_repository = SQLiteTraceRepository(db)
    repository = V2Repository(db)
    registry = AgentRegistry()
    registry.register(P2PlannerAgent())
    registry.register(P2CoderAgent())
    registry.register(P2ReviewerAgent())
    registry.register(P2TesterAgent())
    runtime = OrchestratorRuntime(
        registry=registry,
        trace_repository=trace_repository,
        v2_repository=repository,
    )

    result = runtime.run(
        provider=DummyProvider(),
        model="dummy-model",
        task="做一轮包含 review 的执行",
        session_id="p2-session",
        tool_registry=ToolRegistry(workspace_root=tmp_path),
        workspace_root=tmp_path,
        max_steps=4,
    )
    replay = runtime.get_run_replay(result.run_id or "")

    assert result.status == "completed"
    assert any(item["target_agent"] == "reviewer" for item in replay["delegations"])
    assert any(item["key"] == "review_report" for item in replay["artifacts"])
    assert any(node["node_type"] == "artifact" for node in replay["execution_nodes"])
    assert any(node["node_type"] == "delegation" and "reviewer" in node["label"] for node in replay["execution_nodes"])
    assert "Review 发现问题数：1" in result.final_output
    assert "artifact | review_report" in format_execution_nodes(replay["execution_nodes"])


def test_reviewer_agent_merges_rule_and_llm_review(tmp_path: Path) -> None:
    db = SQLiteDB(tmp_path / "reviewer.sqlite3")
    (tmp_path / "app" / "v1" / "runtime").mkdir(parents=True, exist_ok=True)
    (tmp_path / "app" / "contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "app" / "v1" / "runtime" / "loop.py").write_text(
        "def run_loop():\n    try:\n        pass\n    except Exception:\n        return None\n",
        encoding="utf-8",
    )
    (tmp_path / "app" / "contracts" / "agent.py").write_text(
        "class AgentArtifact:\n    pass\n",
        encoding="utf-8",
    )
    provider = QueueProvider(
        [
            """
            {
              "review_summary": "LLM review 发现需要补测试和边界确认。",
              "issues": [
                {
                  "severity": "medium",
                  "title": "缺少测试改动",
                  "detail": "这次运行修改了代码但没有看到测试变更，需要确认覆盖。",
                  "file_path": null
                },
                {
                  "severity": "high",
                  "title": "触及 v1 代码路径",
                  "detail": "改动触达 v1 目录，建议先做回归验证。",
                  "file_path": "app/v1/runtime/loop.py"
                }
              ],
              "recommended_action": "先补测试并验证 v1 稳定性。"
            }
            """
        ]
    )
    tool_registry = ToolRegistry(workspace_root=tmp_path)
    tool_registry.register(ReadFileTool(workspace_root=tmp_path))
    context = AgentContext(
        provider=provider,
        model="fake-model",
        reasoning_mode="default",
        tool_registry=tool_registry,
        trace_repository=SQLiteTraceRepository(db),
        trace_recorder=JsonlTraceRecorder(run_id="review-run", trace_dir=tmp_path / ".traces"),
        workspace_root=tmp_path,
        session_id="review-session",
        run_id="review-run",
    )
    agent = ReviewerAgent()
    workspace = SharedWorkspace(
        session_id="review-session",
        run_id="review-run",
        user_goal="增强 reviewer",
        project_summary="一个带 v1/v2 双版本结构的工程。",
        latest_patch_summary="修改了共享 contract，并触及 app/v1/runtime/loop.py。",
    )
    task = AgentTask(
        session_id="review-session",
        run_id="review-run",
        goal="Review 最新代码改动，检查明显风险和可维护性问题。",
        step_type="review",
        target_agent="reviewer",
    )

    result = agent.run(
        task=task,
        workspace=workspace,
        context=context,
        prompt_context={
            "project_summary": workspace.project_summary,
            "coder_context": {
                "modified_files": ["app/contracts/agent.py", "app/v1/runtime/loop.py"],
                "created_files": [],
                "deleted_files": [],
                "diff_previews": {
                    "app/v1/runtime/loop.py": "@@ -1,0 +1,4 @@\n+try:\n+    pass\n+except Exception:\n+    return None",
                },
                "risk_notes": [],
            },
            "analysis_context": {
                "key_files": [{"path": "app/v1/runtime/loop.py", "reason": "runtime 主链路"}],
            },
        },
    )

    issues = result.output_data["issues"]
    assert result.output_data["llm_review_used"] is True
    assert "app/v1/runtime/loop.py" in result.output_data["changed_file_snippets"]
    assert "app/v1/runtime/loop.py" in result.output_data["key_file_snippets"]
    assert result.output_data["recommended_action"] == "先补测试并验证 v1 稳定性。"
    assert any(issue["title"] == "缺少测试改动" for issue in issues)
    assert any(issue["title"] == "触及 v1 代码路径" and issue["severity"] == "high" for issue in issues)
    assert any(issue["title"] == "存在宽泛异常捕获" for issue in issues)
    assert "LLM review" in result.summary
