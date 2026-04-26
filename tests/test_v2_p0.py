"""Tests for V2 P0 capabilities."""

from __future__ import annotations

from pathlib import Path

from app.cli.entry import run_agent_task
from app.contracts.agent import AgentResult, AgentTask, SharedWorkspace, TestReport
from app.contracts.message import ChatMessage
from app.contracts.planner import PlanStep
from app.contracts.run import RunChoice, RunMetrics, RunRequest, RunResult, RunUsage
from app.contracts.tool import ToolResult
from app.db.sqlite import SQLiteDB
from app.llm.client import LLMProvider
from app.trace.recorder import JsonlTraceRecorder
from app.trace.repository import SQLiteTraceRepository
from app.v1.tools.registry import ToolRegistry
from app.v2.agents import AnalystAgent, CoderAgent, OrchestratorAgent, PlannerAgent, ReviewerAgent, TesterAgent
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
        self.last_kwargs: dict[str, object] = {}

    def run(self, **kwargs: object) -> RunResult:
        self.last_kwargs = dict(kwargs)
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


def test_planner_agent_routes_retrieve_docs_to_analyst(tmp_path: Path) -> None:
    agent = PlannerAgent()
    step = PlanStep(
        title="检索相关文档",
        goal="先检索相关文档，根据知识库内容准备 OpenCV C++ 直方图匹配算法。",
        type="coding",
        description="使用知识库检索相关算法资料",
        suggested_agent="coder",
        tool_name="retrieve_docs",
    )

    enriched = agent._enrich_step(step)

    assert enriched.type == "analysis"
    assert enriched.suggested_agent == "analyst"
    assert enriched.tool_name == "retrieve_docs"


def test_runtime_infers_analysis_mode_from_step_semantics(tmp_path: Path) -> None:
    runtime = build_default_registry  # keep import used for module coverage
    del runtime
    from app.v2.runtime import OrchestratorRuntime
    from app.v2.registry import AgentRegistry

    orchestrator = OrchestratorRuntime(registry=AgentRegistry(), trace_repository=SQLiteTraceRepository(SQLiteDB(tmp_path / "mode.sqlite3")))
    directory_step = type("Step", (), {"type": "analysis", "title": "查看目录结构", "goal": "识别顶层目录", "tool_name": "list_dir"})()
    key_file_step = type("Step", (), {"type": "analysis", "title": "读取关键文件", "goal": "读取配置和入口文件", "tool_name": "read_file"})()
    summary_step = type("Step", (), {"type": "analysis", "title": "总结结构", "goal": "总结模块职责", "tool_name": None})()

    assert orchestrator._build_step_input(directory_step)["analysis_mode"] == "directory_scan"
    assert orchestrator._build_step_input(key_file_step)["analysis_mode"] == "key_file_read"
    assert orchestrator._build_step_input(summary_step)["analysis_mode"] == "summary"


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


def test_tester_agent_prefers_gradle_kotlin_validation_from_analysis_context() -> None:
    tester = TesterAgent()
    task = AgentTask(
        session_id="test-session",
        run_id="test-run",
        goal="验证登录修复",
        step_type="testing",
        target_agent="tester",
    )

    candidates = tester._select_command_candidates(
        task=task,
        prompt_context={
            "project_summary": "这是一个 Gradle/Kotlin 项目。",
            "analysis_context": {
                "repo_profile": "gradle_kotlin",
                "root_entries": [
                    {"name": "gradlew", "type": "file"},
                    {"name": "build.gradle.kts", "type": "file"},
                ],
            },
            "coder_context": {},
        },
    )

    assert candidates[:3] == ["./gradlew compileKotlin", "./gradlew compileKotlinJvm", "./gradlew test"]
    assert "pytest -q" not in candidates[:3]


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


def test_analyst_agent_prioritizes_gradle_kotlin_files(tmp_path: Path) -> None:
    provider = QueueProvider([])
    context = _make_context(tmp_path, provider)
    context.tool_registry.register_default_tools()
    (tmp_path / "README.md").write_text("# Monica\n", encoding="utf-8")
    (tmp_path / "build.gradle.kts").write_text("plugins { kotlin(\"jvm\") version \"2.0.0\" }\n", encoding="utf-8")
    (tmp_path / "settings.gradle.kts").write_text("rootProject.name = \"Monica\"\n", encoding="utf-8")
    (tmp_path / "src" / "main" / "kotlin").mkdir(parents=True)
    (tmp_path / "src" / "main" / "kotlin" / "Main.kt").write_text(
        "fun main() { println(\"Monica\") }\n",
        encoding="utf-8",
    )
    (tmp_path / "domain").mkdir()
    (tmp_path / "domain" / "Layer.kt").write_text("class Layer\n", encoding="utf-8")

    agent = AnalystAgent()
    workspace = SharedWorkspace(session_id="test-session", run_id="test-run", user_goal="分析 Kotlin 项目")
    task = AgentTask(
        session_id="test-session",
        run_id="test-run",
        goal="读取关键文件并分析项目结构",
        step_type="analysis",
        target_agent="analyst",
        input_data={"tool_name": "read_file"},
    )

    result = agent.run(
        task=task,
        workspace=workspace,
        context=context,
        prompt_context={"analysis_context": {}},
    )

    key_paths = [item["path"] for item in result.output_data["key_files"]]
    assert result.status == "completed"
    assert "build.gradle.kts" in key_paths
    assert "settings.gradle.kts" in key_paths
    assert any(path.endswith(".kt") for path in key_paths)
    assert not any(path.startswith("app/") for path in key_paths)
    assert any(path.endswith(".kts") for path in result.output_data["entry_files"])


def test_analyst_agent_summary_mode_uses_existing_context(tmp_path: Path) -> None:
    provider = QueueProvider([])
    context = _make_context(tmp_path, provider)
    context.tool_registry.register_default_tools()
    (tmp_path / "README.md").write_text("# Monica\n", encoding="utf-8")
    (tmp_path / "build.gradle.kts").write_text("plugins { kotlin(\"jvm\") version \"2.0.0\" }\n", encoding="utf-8")
    (tmp_path / "settings.gradle.kts").write_text("rootProject.name = \"Monica\"\n", encoding="utf-8")

    agent = AnalystAgent()
    workspace = SharedWorkspace(session_id="test-session", run_id="test-run", user_goal="总结项目结构")
    task = AgentTask(
        session_id="test-session",
        run_id="test-run",
        goal="总结目录结构、模块职责和开发约定",
        step_type="analysis",
        target_agent="analyst",
        input_data={"tool_name": "summary", "analysis_mode": "summary"},
    )

    result = agent.run(
        task=task,
        workspace=workspace,
        context=context,
        prompt_context={
            "analysis_context": {
                "project_summary": "前序分析指出这是一个 Gradle Kotlin 项目。",
                "key_files": [{"path": "build.gradle.kts", "reason": "构建入口"}],
            }
        },
    )

    assert result.status == "completed"
    assert "前序分析结论" in result.output_data["project_summary"]
    assert "build.gradle.kts" in [item["path"] for item in result.output_data["key_files"]]
    assert result.metrics is not None
    assert result.metrics.tool_call_count >= 1


def test_analyst_agent_uses_retrieve_docs_mode(tmp_path: Path) -> None:
    provider = QueueProvider([])
    context = _make_context(tmp_path, provider)
    context.tool_registry.register_default_tools()
    called: list[tuple[str, dict[str, object]]] = []
    original_execute_tool = context.tool_registry.execute_tool

    def fake_execute_tool(*, tool_name: str, arguments: dict[str, object], tool_call_id: str = "direct-tool-call") -> ToolResult:
        called.append((tool_name, arguments))
        if tool_name == "retrieve_docs":
            return ToolResult(
                tool_call_id=tool_call_id,
                name=tool_name,
                content=(
                    '{"query":"OpenCV C++ 直方图匹配","rag_id":"opencv_algo","match_count":1,'
                    '"matches":[{"title":"Histogram Matching",'
                    '"content":"Use cv::calcHist, normalize CDFs, build a lookup table, then cv::LUT."}]}'
                ),
            )
        return original_execute_tool(tool_name=tool_name, arguments=arguments, tool_call_id=tool_call_id)

    context.tool_registry.execute_tool = fake_execute_tool  # type: ignore[method-assign]
    agent = AnalystAgent()
    workspace = SharedWorkspace(session_id="test-session", run_id="test-run", user_goal="写 OpenCV 算法")
    task = AgentTask(
        session_id="test-session",
        run_id="test-run",
        goal="先检索相关文档根据知识库内容，写一个 OpenCV C++ 直方图匹配的算法。",
        step_type="analysis",
        target_agent="analyst",
        input_data={"tool_name": "retrieve_docs", "rag_id": "opencv_algo"},
    )

    result = agent.run(task=task, workspace=workspace, context=context, prompt_context={})

    assert result.status == "completed"
    assert result.output_data["analysis_mode"] == "rag_retrieval"
    assert result.output_data["docs_context"]["match_count"] == 1
    assert result.output_data["docs_context"]["rag_id"] == "opencv_algo"
    assert any(
        name == "retrieve_docs" and args.get("rag_id") == "opencv_algo"
        for name, args in called
    )
    assert any(name == "retrieve_docs" for name, _ in called)
    assert "知识库检索命中 1 条相关片段" in result.output_data["project_summary"]
    assert result.output_data["key_files"] == []


def test_workspace_merge_preserves_docs_context() -> None:
    from app.v2.workspace import WorkspaceStore

    workspace = SharedWorkspace(session_id="test-session", run_id="test-run", user_goal="写算法")
    store = WorkspaceStore(workspace)

    store.merge_analyst_context(
        {
            "project_summary": "知识库检索完成。",
            "analysis_mode": "rag_retrieval",
            "docs_context": {
                "query": "OpenCV 直方图匹配",
                "rag_id": "opencv_algo",
                "match_count": 1,
                "matches": [{"title": "Histogram Matching", "content": "calcHist + CDF + LUT"}],
            },
        }
    )
    merged = store.merge_analyst_context(
        {
            "project_summary": "总结完成。",
            "analysis_mode": "summary",
            "key_files": [{"path": "README.md", "reason": "项目说明"}],
        }
    )

    assert merged["docs_context"]["match_count"] == 1
    assert merged["docs_context"]["rag_id"] == "opencv_algo"
    assert merged["docs_context"]["matches"][0]["title"] == "Histogram Matching"


def test_coder_prompt_uses_docs_context_for_algorithm_answers(tmp_path: Path) -> None:
    agent = CoderAgent(agent_loop=FakeCoderLoop(tmp_path))
    workspace = SharedWorkspace(session_id="test-session", run_id="test-run", user_goal="写 OpenCV 算法")
    task = AgentTask(
        session_id="test-session",
        run_id="test-run",
        goal="根据知识库内容，写一个 OpenCV C++ 直方图匹配的算法。",
        step_type="coding",
        target_agent="coder",
    )

    prompt = agent._build_task_prompt(
        task=task,
        prompt_context={
            "analysis_context": {
                "docs_context": {
                    "query": "OpenCV C++ 直方图匹配",
                    "match_count": 1,
                    "matches": [
                        {
                            "title": "Histogram Matching",
                            "content": "Use cv::calcHist, normalize CDFs, build a lookup table, then cv::LUT.",
                        }
                    ],
                }
            }
        },
        workspace=workspace,
    )

    assert "知识库检索结果" in prompt
    assert "C++ 示例代码" in prompt
    assert "不要反问缺少具体编程任务" in prompt
    assert "未写入文件" in prompt


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
    assert agent.agent_loop.last_kwargs["is_top_level"] is False
    assert agent.agent_loop.last_kwargs["parent_run_id"] == "test-run"
    assert "app/sample.py" in result.output_data["created_files"] or "app/sample.py" in result.output_data["modified_files"]
    assert result.output_data["patch_id"]
    assert result.output_data["base_snapshot_id"]
    assert result.output_data["head_snapshot_id"]
    assert result.output_data["patch_stats"]["files_changed"] >= 1
    assert result.output_data["patch_stats"]["insertions"] >= 2
    assert "app/sample.py" in result.output_data["patch_diffs"]
    assert result.output_data["patch_artifact"]["schema_version"] == "v2.patch_artifact.v1"
    assert result.output_data["patch_artifact"]["stats"] == result.output_data["patch_stats"]
    assert result.output_data["loop_boundary"]["is_second_orchestrator"] is False
    assert result.output_data["loop_boundary"]["delegation_allowed"] is False
    assert "不拥有多 Agent 调度权" in result.output_data["loop_boundary"]["explanation"]
    assert any(artifact.key == "patch_summary" and artifact.content["patch_id"] for artifact in result.artifacts)
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


def test_reviewer_agent_links_failed_test_result_and_security_rules(tmp_path: Path) -> None:
    provider = QueueProvider([])
    context = _make_context(tmp_path, provider)
    context.tool_registry.register_default_tools()
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "auth.py").write_text(
        "def login(username, password):\n    return eval(password)\n",
        encoding="utf-8",
    )
    agent = ReviewerAgent()
    workspace = SharedWorkspace(
        session_id="test-session",
        run_id="test-run",
        user_goal="修复登录 bug",
        latest_patch_summary="已修改 app/auth.py，登录逻辑修复完成，测试通过。",
        latest_test_result=TestReport(
            status="failed",
            executed_command="pytest -q tests/test_auth.py",
            summary="认证测试失败。",
            failure_type="assertion_error",
            key_logs=["AssertionError: login failed"],
        ),
    )
    task = AgentTask(
        session_id="test-session",
        run_id="test-run",
        goal="review patch",
        step_type="review",
        target_agent="reviewer",
        input_data={"review_strategy": {"llm_enabled": False, "strictness": "strict", "focus_areas": ["security"]}},
    )

    result = agent.run(
        task=task,
        workspace=workspace,
        context=context,
        prompt_context={
            "coder_context": {
                "modified_files": ["app/auth.py"],
                "diff_previews": {"app/auth.py": "+def login(username, password):\n+    return eval(password)"},
            },
            "latest_test_result": workspace.latest_test_result.model_dump(),
            "project_summary": "认证模块项目",
        },
    )

    issues = result.output_data["issues"]
    assert result.output_data["llm_review_used"] is False
    assert result.output_data["review_strategy"]["strictness"] == "strict"
    assert result.output_data["review_strategy"]["rule_groups"] == [
        "scope",
        "testing",
        "security",
        "maintainability",
        "boundaries",
        "api",
        "domain",
    ]
    assert result.output_data["rule_group_counts"]["testing"] >= 2
    assert result.output_data["rule_group_counts"]["security"] >= 1
    assert any(issue["title"] == "测试失败仍未解决" and issue["severity"] == "high" for issue in issues)
    assert any(issue["title"] == "测试失败仍未解决" and issue["category"] == "testing" for issue in issues)
    assert any(issue["title"] == "危险动态执行" and issue["severity"] == "high" for issue in issues)
    assert any(issue["title"] == "危险动态执行" and issue["category"] == "security" for issue in issues)
    assert any(issue["title"] == "认证或存储改动缺少测试覆盖" for issue in issues)
    assert any(issue["title"] == "缺少测试改动" and issue["severity"] == "high" for issue in issues)


def test_reviewer_agent_rule_groups_and_test_failure_mode_are_configurable(tmp_path: Path) -> None:
    provider = QueueProvider([])
    context = _make_context(tmp_path, provider)
    context.tool_registry.register_default_tools()
    agent = ReviewerAgent()
    workspace = SharedWorkspace(
        session_id="test-session",
        run_id="test-run",
        user_goal="修复支付 bug",
        latest_patch_summary="修改了 payment.py。",
        latest_test_result=TestReport(
            status="failed",
            executed_command="pytest -q tests/test_payment.py",
            summary="支付测试失败。",
            failure_type="assertion_error",
            key_logs=["AssertionError"],
        ),
    )
    task = AgentTask(
        session_id="test-session",
        run_id="test-run",
        goal="review patch",
        step_type="review",
        target_agent="reviewer",
        input_data={
            "review_strategy": {
                "llm_enabled": False,
                "rule_groups": ["testing"],
                "test_failure_mode": "suggest",
            }
        },
    )

    result = agent.run(
        task=task,
        workspace=workspace,
        context=context,
        prompt_context={
            "coder_context": {
                "modified_files": ["payment.py"],
                "diff_previews": {"payment.py": "+def pay(user_input):\n+    return eval(user_input)"},
            },
            "latest_test_result": workspace.latest_test_result.model_dump(),
        },
    )

    issues = result.output_data["issues"]
    assert result.output_data["review_strategy"]["rule_groups"] == ["testing"]
    assert result.output_data["review_strategy"]["test_failure_mode"] == "suggest"
    assert any(issue["title"] == "测试失败仍未解决" and issue["severity"] == "medium" for issue in issues)
    assert any(issue["title"] == "缺少测试改动" for issue in issues)
    assert not any(issue["title"] == "危险动态执行" for issue in issues)
    assert set(result.output_data["rule_group_counts"]) == {"testing"}


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


def test_orchestrator_agent_exposes_identity_and_policy(tmp_path: Path) -> None:
    agent = OrchestratorAgent()
    context = _make_context(tmp_path, QueueProvider([]))
    workspace = SharedWorkspace(session_id="test-session", run_id="test-run", user_goal="demo")
    task = AgentTask(
        session_id="test-session",
        run_id="test-run",
        goal="prepare orchestrator policy",
        step_type="orchestration",
        target_agent="orchestrator",
    )

    result = agent.run(
        task=task,
        workspace=workspace,
        context=context,
        prompt_context={
            "enabled_agents": ["planner", "analyst", "coder"],
            "max_steps": 8,
            "max_replans": 1,
            "run_timeout_seconds": 120,
            "review_strategy": {"strictness": "normal"},
        },
    )

    policy = result.output_data["policy"]
    strategy_profile = result.output_data["strategy_profile"]
    assert result.status == "completed"
    assert result.agent_id == "orchestrator"
    assert policy["delegation_model"] == "orchestrator_only"
    assert policy["sub_agent_delegation_allowed"] is False
    assert policy["enabled_agents"] == ["analyst", "coder", "planner"]
    assert "Orchestrator Agent" in result.output_data["system_prompt"]
    assert strategy_profile["name"] == "fast_fix"
    assert strategy_profile["tester_enabled"] is False
    assert any(artifact.key == "orchestrator_strategy_profile" for artifact in result.artifacts)


def test_planner_replan_fallback_uses_failure_context(tmp_path: Path) -> None:
    provider = QueueProvider(["not json"])
    context = _make_context(tmp_path, provider)
    agent = PlannerAgent()
    workspace = SharedWorkspace(
        session_id="test-session",
        run_id="test-run",
        user_goal="修复登录 bug",
        latest_patch_summary="已修改登录模块。",
        latest_test_result=TestReport(
            status="failed",
            executed_command="pytest -q tests/test_auth.py",
            summary="登录断言失败。",
            failure_type="assertion_error",
            key_logs=["AssertionError"],
        ),
    )
    task = AgentTask(
        session_id="test-session",
        run_id="test-run",
        goal="根据失败结果重新规划",
        step_type="planning",
        target_agent="planner",
        input_data={
            "replan_context": {
                "failed_agent": "tester",
                "failure_summary": "登录断言失败。",
            }
        },
    )

    result = agent.run(
        task=task,
        workspace=workspace,
        context=context,
        prompt_context={
            "task_input": task.input_data,
            "orchestrator_context": {
                "policy": {"enabled_agents": ["orchestrator", "planner", "coder", "tester"]}
            },
            "latest_test_result": workspace.latest_test_result.model_dump(),
        },
    )

    plan = result.output_data["plan"]
    assert [step["suggested_agent"] for step in plan["steps"]] == ["coder", "tester"]
    assert plan["metadata"]["planner_strategy"]["mode"] == "replan"
    assert plan["metadata"]["planner_strategy"]["rag_shortcut_applied"] is False
    assert "Tester 失败" in plan["steps"][0]["strategy_explanation"]
    assert plan["steps"][0]["replan_reason"] == "登录断言失败。"


def test_planner_metadata_marks_rag_shortcut_applied(tmp_path: Path) -> None:
    provider = QueueProvider(["not json"])
    context = _make_context(tmp_path, provider)
    agent = PlannerAgent()
    workspace = SharedWorkspace(session_id="test-session", run_id="test-run", user_goal="写算法")
    task = AgentTask(
        session_id="test-session",
        run_id="test-run",
        goal="先检索相关文档根据知识库内容，写一个 OpenCV C++ 直方图匹配的算法。",
        step_type="planning",
        target_agent="planner",
    )

    result = agent.run(
        task=task,
        workspace=workspace,
        context=context,
        prompt_context={},
    )

    strategy = result.output_data["plan"]["metadata"]["planner_strategy"]
    assert strategy["mode"] == "initial_plan"
    assert strategy["rag_shortcut_applied"] is True
    assert strategy["selected_rag_id"] == "default"


def test_planner_metadata_includes_selected_rag_id(tmp_path: Path) -> None:
    provider = QueueProvider(["not json"])
    context = _make_context(tmp_path, provider)
    agent = PlannerAgent()
    workspace = SharedWorkspace(session_id="test-session", run_id="test-run", user_goal="写算法")
    task = AgentTask(
        session_id="test-session",
        run_id="test-run",
        goal="先检索相关文档根据知识库内容，写一个 OpenCV C++ 直方图匹配的算法。",
        step_type="planning",
        target_agent="planner",
        input_data={"rag_id": "opencv_algo", "rag_ids": ["opencv_algo", "backend_java"]},
    )

    result = agent.run(
        task=task,
        workspace=workspace,
        context=context,
        prompt_context={"task_input": {"rag_id": "opencv_algo", "rag_ids": ["opencv_algo", "backend_java"]}},
    )

    strategy = result.output_data["plan"]["metadata"]["planner_strategy"]
    assert strategy["selected_rag_id"] == "opencv_algo"
    assert strategy["selected_rag_ids"] == ["opencv_algo", "backend_java"]


def test_build_default_registry_supports_reviewer_toggle() -> None:
    with_reviewer = build_default_registry(enable_reviewer=True)
    without_reviewer = build_default_registry(enable_reviewer=False)

    assert with_reviewer.get("orchestrator") is not None
    assert with_reviewer.get("reviewer") is not None
    assert without_reviewer.get("reviewer") is None


def test_describe_agent_matrix_contains_core_roles() -> None:
    matrix = describe_agent_matrix()
    roles = {item["role"] for item in matrix}
    assert {"orchestrator", "planner", "analyst", "coder", "tester", "reviewer"}.issubset(roles)
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
