"""V1 regression tests to guard against V2 changes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.routes.agent import AgentRunRequest, run_agent
from app.api.routes.debug import (
    RagDeleteSourceRequest,
    RagUploadRequest,
    delete_rag_source,
    get_rag_overview,
    upload_rag_file,
)
from app.cli.entry import run_agent_task
from app.contracts.message import ChatMessage
from app.contracts.planner import PlanStep
from app.contracts.run import RunChoice, RunRequest, RunResult
from app.contracts.tool import ToolCall, ToolFunction
from app.contracts.trace import TraceEvent
from app.llm.client import LLMProvider, OpenAICompatibleProvider
from app.trace.repository import SQLiteTraceRepository
from app.v1.memory.repository import SQLiteMemoryRepository
from app.v1.memory.session_memory import SessionMemory
from app.v1.memory.summary_memory import SummaryMemory
from app.v1.planner.base import Planner
from app.v1.planner.simple_planner import SimplePlanner
from app.v1.runtime.direct_tool_executor import DirectToolExecutor
from app.v1.runtime.loop import AgentLoop
from app.v1.runtime.plan_executor import PlanExecutor
from app.v1.runtime.write_intent_parser import WriteIntentParser
from app.v1.tools.list_dir import ListDirTool
from app.v1.tools.read_file import ReadFileTool
from app.v1.tools.retrieve_docs import RetrieveDocsTool
from app.v1.tools.registry import ToolRegistry
from app.v1.tools.write_file import WriteFileTool
from app.core.exceptions import RagIdValidationError
from app.v1.rag.rag_id_policy import strict_normalize_v2_rag_ids
from app.v1.rag.retriever import DocumentRetriever
from app.v1.rag.vector_store import ChromaVectorStore, normalize_rag_id_value


class StaticProvider(LLMProvider):
    """Return deterministic assistant messages for V1 regression tests."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._index = 0

    def chat(self, chat_request: RunRequest) -> RunResult:
        if self._index >= len(self._responses):  # pragma: no cover - defensive
            raise AssertionError("No more fake responses configured.")
        content = self._responses[self._index]
        self._index += 1
        return RunResult(
            id=f"fake-run-{self._index}",
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


class SingleStepPlanner(Planner):
    """A tiny planner used to isolate V1 plan execution behaviour."""

    def should_plan(self, task: str) -> bool:
        return True

    def create_plan(self, task: str) -> list[PlanStep]:
        return [
            PlanStep(
                title="给出当前结论",
                goal=task,
                description="只基于当前任务输出一步结果。",
                success_criteria=["返回步骤结论"],
            )
        ]


def _register_lightweight_tools(registry: ToolRegistry, *args: object, **kwargs: object) -> None:
    """Register a minimal tool set without RAG-heavy initialization."""
    _ = args, kwargs
    registry.register_dummy_tool()
    registry.register(ReadFileTool(workspace_root=registry.workspace_root))
    registry.register(ListDirTool(workspace_root=registry.workspace_root))


def test_retrieve_docs_tool_accepts_rag_id_when_multi_rag_enabled() -> None:
    class FakeRetriever:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def retrieve(
            self,
            *,
            query: str,
            top_k: int = 3,
            min_score: float = 0.0,
            rerank: bool = True,
            fetch_k: int | None = None,
            rag_id: str | None = None,
            rag_ids: list[str] | None = None,
        ) -> list[dict[str, object]]:
            self.calls.append(
                {
                    "query": query,
                    "top_k": top_k,
                    "min_score": min_score,
                    "rerank": rerank,
                    "fetch_k": fetch_k,
                    "rag_id": rag_id,
                    "rag_ids": rag_ids,
                }
            )
            return [{"source": "docs/a.md", "content": "demo", "score": 0.9, "rag_id": rag_id or "default"}]

    fake = FakeRetriever()
    tool = RetrieveDocsTool(retriever=fake, allow_multi_rag=True)  # type: ignore[arg-type]

    result = tool.execute(
        {
            "query": "opencv histogram matching",
            "top_k": 2,
            "rag_id": "opencv_algo",
        },
        tool_call_id="test-call",
    )

    assert result.is_error is False
    assert fake.calls and fake.calls[0]["rag_id"] == "opencv_algo"
    payload = json.loads(result.content)
    assert payload["rag_id"] == "opencv_algo"


def test_retrieve_docs_tool_supports_multi_rag_merge_when_enabled() -> None:
    class FakeRetriever:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def retrieve(
            self,
            *,
            query: str,
            top_k: int = 3,
            min_score: float = 0.0,
            rerank: bool = True,
            fetch_k: int | None = None,
            rag_id: str | None = None,
            rag_ids: list[str] | None = None,
        ) -> list[dict[str, object]]:
            self.calls.append(
                {
                    "query": query,
                    "top_k": top_k,
                    "min_score": min_score,
                    "rerank": rerank,
                    "fetch_k": fetch_k,
                    "rag_id": rag_id,
                    "rag_ids": rag_ids,
                }
            )
            return [
                {"source": "docs/a.md", "content": "demo-a", "score": 0.9, "rag_id": "product_docs"},
                {"source": "docs/b.md", "content": "demo-b", "score": 0.8, "rag_id": "backend_java"},
            ]

    fake = FakeRetriever()
    tool = RetrieveDocsTool(retriever=fake, allow_multi_rag=True)  # type: ignore[arg-type]

    result = tool.execute(
        {
            "query": "login flow",
            "top_k": 4,
            "rag_ids": ["product_docs", "backend_java"],
        },
        tool_call_id="test-call-multi",
    )

    assert result.is_error is False
    assert fake.calls and fake.calls[0]["rag_ids"] == ["product_docs", "backend_java"]
    payload = json.loads(result.content)
    assert payload["rag_ids"] == ["product_docs", "backend_java"]
    assert payload["match_count"] == 2


def test_v1_retrieve_docs_tool_forces_default_when_multi_rag_disabled() -> None:
    class FakeRetriever:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def retrieve(
            self,
            *,
            query: str,
            top_k: int = 3,
            min_score: float = 0.0,
            rerank: bool = True,
            fetch_k: int | None = None,
            rag_id: str | None = None,
            rag_ids: list[str] | None = None,
        ) -> list[dict[str, object]]:
            self.calls.append(
                {
                    "query": query,
                    "top_k": top_k,
                    "min_score": min_score,
                    "rerank": rerank,
                    "fetch_k": fetch_k,
                    "rag_id": rag_id,
                    "rag_ids": rag_ids,
                }
            )
            return [{"source": "docs/a.md", "content": "demo", "score": 0.9, "rag_id": "default"}]

    fake = FakeRetriever()
    tool = RetrieveDocsTool(retriever=fake, allow_multi_rag=False)  # type: ignore[arg-type]

    result = tool.execute(
        {
            "query": "ignored routing",
            "rag_id": "custom",
            "rag_ids": ["a", "b"],
        },
        tool_call_id="test-call",
    )

    assert result.is_error is False
    assert fake.calls and fake.calls[0]["rag_id"] is None and fake.calls[0]["rag_ids"] is None
    payload = json.loads(result.content)
    assert payload["rag_id"] == "default"
    assert payload["rag_ids"] == ["default"]


def test_retrieve_docs_tool_defaults_to_single_rag() -> None:
    class FakeRetriever:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def retrieve(
            self,
            *,
            query: str,
            top_k: int = 3,
            min_score: float = 0.0,
            rerank: bool = True,
            fetch_k: int | None = None,
            rag_id: str | None = None,
            rag_ids: list[str] | None = None,
        ) -> list[dict[str, object]]:
            self.calls.append({"rag_id": rag_id, "rag_ids": rag_ids})
            return [{"source": "docs/a.md", "content": query, "score": 0.9, "rag_id": "default"}]

    fake = FakeRetriever()
    tool = RetrieveDocsTool(retriever=fake)  # type: ignore[arg-type]

    result = tool.execute({"query": "single rag", "rag_id": "custom", "rag_ids": ["a", "b"]}, "test-call")

    assert result.is_error is False
    assert fake.calls == [{"rag_id": None, "rag_ids": None}]
    payload = json.loads(result.content)
    assert payload["rag_id"] == "default"
    assert payload["rag_ids"] == ["default"]


def test_v1_tool_registry_retrieve_docs_omits_rag_params_when_single_rag(tmp_path: Path) -> None:
    registry = ToolRegistry(workspace_root=tmp_path)
    registry.register_default_tools(multi_rag=False)
    defs = registry.get_tool_definitions()
    rd = next(d for d in defs if d.name == "retrieve_docs")
    props = rd.parameters["properties"]
    assert "rag_id" not in props
    assert "rag_ids" not in props


def test_tool_registry_defaults_retrieve_docs_to_single_rag(tmp_path: Path) -> None:
    registry = ToolRegistry(workspace_root=tmp_path)
    registry.register_default_tools()
    defs = registry.get_tool_definitions()
    rd = next(d for d in defs if d.name == "retrieve_docs")
    props = rd.parameters["properties"]
    assert "rag_id" not in props
    assert "rag_ids" not in props


def test_v1_api_basic_path_still_works(monkeypatch, tmp_path: Path) -> None:
    repository = SQLiteMemoryRepository(tmp_path / "api-memory.sqlite3")
    provider = StaticProvider(["v1 api still works"])

    monkeypatch.setattr("app.api.routes.agent.get_provider", lambda **_: provider)
    monkeypatch.setattr("app.api.routes.agent.get_session_memory", lambda: SessionMemory(repository))
    monkeypatch.setattr("app.api.routes.agent.get_summary_memory", lambda: SummaryMemory(repository))
    monkeypatch.setattr(
        "app.api.routes.agent.get_trace_repository",
        lambda: SQLiteTraceRepository(repository.db),
    )
    monkeypatch.setattr("app.api.routes.agent.get_agent_loop", lambda: AgentLoop())
    monkeypatch.setattr("app.api.routes.agent.get_planner", lambda: SimplePlanner())
    monkeypatch.setattr(
        ToolRegistry,
        "register_default_tools",
        _register_lightweight_tools,
    )

    response = run_agent(
        AgentRunRequest(
            task="hello",
            version="v1",
            model="fake-model",
            api_key="fake-key",
            workdir=str(tmp_path),
            include_trace=True,
        )
    )

    assert response.version == "v1"
    assert response.status == "completed"
    assert response.answer == "v1 api still works"
    assert response.step_count == 1
    assert any(event["event_type"] == "run_started" for event in response.trace)
    assert any(event["event_type"] == "run_finished" for event in response.trace)


def test_v1_api_rejects_multi_rag_parameters() -> None:
    with pytest.raises(HTTPException) as excinfo:
        run_agent(
            AgentRunRequest(
                task="hello",
                version="v1",
                model="fake-model",
                api_key="fake-key",
                rag_ids=["product_docs", "backend_java"],
            )
        )
    assert excinfo.value.status_code == 400
    assert "v1 不支持多向量库参数 rag_ids" in str(excinfo.value.detail)


def test_v1_api_rejects_non_default_rag_id() -> None:
    with pytest.raises(HTTPException) as excinfo:
        run_agent(
            AgentRunRequest(
                task="hello",
                version="v1",
                model="fake-model",
                api_key="fake-key",
                rag_id="product_docs",
            )
        )
    assert excinfo.value.status_code == 400
    assert "v1 仅支持默认向量库（default）" in str(excinfo.value.detail)


def test_v1_cli_basic_path_still_works(monkeypatch, tmp_path: Path) -> None:
    repository = SQLiteMemoryRepository(tmp_path / "cli-memory.sqlite3")

    class FakeOpenAICompatibleProvider(StaticProvider):
        def __init__(self, **_: object) -> None:
            super().__init__(["v1 cli still works"])

    monkeypatch.setattr("app.cli.entry.OpenAICompatibleProvider", FakeOpenAICompatibleProvider)
    monkeypatch.setattr("app.cli.entry.SQLiteMemoryRepository", lambda: repository)
    monkeypatch.setattr(
        ToolRegistry,
        "register_default_tools",
        _register_lightweight_tools,
    )

    result, version, session_id, trace_lines = run_agent_task(
        task="hello from cli",
        version="v1",
        model="fake-model",
        reasoning_mode="default",
        base_url="https://example.invalid",
        api_key="fake-key",
        service_token="",
        system_prompt="You are helpful.",
        temperature=0.0,
        session_id="cli-session",
        workdir=str(tmp_path),
        max_steps=3,
        run_timeout_seconds=30,
        include_trace=True,
    )

    assert version == "v1"
    assert session_id.startswith("cli-session@")
    assert result.status == "completed"
    assert result.final_output == "v1 cli still works"
    assert any(line.startswith("run_started:") for line in trace_lines)
    assert any(line.startswith("run_finished:") for line in trace_lines)


def test_v1_timeout_after_successful_write_returns_partial_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repository = SQLiteMemoryRepository(tmp_path / "timeout-partial.sqlite3")
    tool_registry = ToolRegistry(workspace_root=tmp_path)
    tool_registry.register(WriteFileTool(workspace_root=tmp_path))

    class WriteThenTimeoutProvider(LLMProvider):
        def chat(self, chat_request: RunRequest) -> RunResult:
            return RunResult(
                id="write-then-timeout",
                model=chat_request.model,
                reasoning_mode=chat_request.reasoning_mode,
                choices=[
                    RunChoice(
                        index=0,
                        message=ChatMessage(
                            role="assistant",
                            content=None,
                            tool_calls=[
                                ToolCall(
                                    id="tool-call-write-1",
                                    function=ToolFunction(
                                        name="write_file",
                                        arguments='{"path":"out/result.txt","content":"hello"}',
                                    ),
                                )
                            ],
                        ),
                        finish_reason="tool_calls",
                    )
                ],
            )

    monotonic_values = iter([0.0, 0.0, 125.0, 125.0])
    monkeypatch.setattr("app.v1.runtime.loop.monotonic", lambda: next(monotonic_values))

    result = AgentLoop().run(
        provider=WriteThenTimeoutProvider(),
        model="fake-model",
        task="先写文件，再总结",
        system_prompt="You are helpful.",
        session_id="timeout-session",
        tool_registry=tool_registry,
        session_memory=SessionMemory(repository),
        summary_memory=SummaryMemory(repository),
        max_steps=3,
        run_timeout_seconds=120,
    )

    assert result.status == "partial_completed"
    assert "已完成部分工作" in result.final_output
    assert "out/result.txt" in result.final_output
    assert (tmp_path / "out" / "result.txt").read_text(encoding="utf-8") == "hello"


def test_v1_plan_executor_treats_partial_step_as_summarizable(tmp_path: Path) -> None:
    class PlannerWithOneExecutionStep(Planner):
        def should_plan(self, task: str) -> bool:
            return True

        def create_plan(self, task: str) -> list[PlanStep]:
            return [
                PlanStep(
                    title="生成实现",
                    goal=task,
                    description="生成并写入实现",
                )
            ]

    call_count = 0

    def fake_run_callable(**kwargs: object) -> RunResult:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return RunResult(
                id="partial-step",
                model="fake-model",
                reasoning_mode="default",
                choices=[RunChoice(index=0, message=ChatMessage(role="assistant", content="已写入文件，但总结超时。"))],
                run_id="partial-step-run",
                session_id=str(kwargs["session_id"]),
                step_count=1,
                status="partial_completed",
                final_output="已写入文件，但总结超时。",
            )
        return RunResult(
            id="summary-step",
            model="fake-model",
            reasoning_mode="default",
            choices=[RunChoice(index=0, message=ChatMessage(role="assistant", content="最终总结可正常输出。"))],
            run_id="summary-step-run",
            session_id=str(kwargs["session_id"]),
            step_count=1,
            status="completed",
            final_output="最终总结可正常输出。",
        )

    executor = PlanExecutor(
        run_callable=fake_run_callable,
        direct_tool_executor=DirectToolExecutor(write_intent_parser=WriteIntentParser()),
    )
    repository = SQLiteMemoryRepository(tmp_path / "plan-partial.sqlite3")

    result = executor.run_with_plan(
        provider=StaticProvider(["unused"]),
        model="fake-model",
        task="写一个实现并汇总",
        system_prompt="You are helpful.",
        session_id="plan-partial-session",
        planner=PlannerWithOneExecutionStep(),
        session_memory=SessionMemory(repository),
        summary_memory=SummaryMemory(repository),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
        max_steps=3,
        run_timeout_seconds=120,
    )

    assert result.status == "completed"
    assert result.final_output == "最终总结可正常输出。"
    assert result.plan[0].status == "completed"


def test_v1_summary_plan_step_disables_tools(tmp_path: Path) -> None:
    class PlannerWithSummaryStep(Planner):
        def should_plan(self, task: str) -> bool:
            return True

        def create_plan(self, task: str) -> list[PlanStep]:
            return [
                PlanStep(
                    title="总结结果",
                    goal=task,
                    description="整理最终结论、产物或建议。",
                )
            ]

    observed_tool_counts: list[int] = []

    def fake_run_callable(**kwargs: object) -> RunResult:
        tool_registry = kwargs["tool_registry"]
        observed_tool_counts.append(len(tool_registry.get_tool_definitions()) if tool_registry is not None else -1)
        return RunResult(
            id="summary-no-tools",
            model="fake-model",
            reasoning_mode="default",
            choices=[RunChoice(index=0, message=ChatMessage(role="assistant", content="总结已完成。"))],
            run_id="summary-no-tools-run",
            session_id=str(kwargs["session_id"]),
            step_count=1,
            status="completed",
            final_output="总结已完成。",
        )

    executor = PlanExecutor(
        run_callable=fake_run_callable,
        direct_tool_executor=DirectToolExecutor(write_intent_parser=WriteIntentParser()),
    )
    repository = SQLiteMemoryRepository(tmp_path / "summary-no-tools.sqlite3")
    tool_registry = ToolRegistry(workspace_root=tmp_path)
    _register_lightweight_tools(tool_registry)

    result = executor.run_with_plan(
        provider=StaticProvider(["unused"]),
        model="fake-model",
        task="整理最终总结",
        system_prompt="You are helpful.",
        session_id="summary-step-session",
        planner=PlannerWithSummaryStep(),
        session_memory=SessionMemory(repository),
        summary_memory=SummaryMemory(repository),
        tool_registry=tool_registry,
        max_steps=3,
        run_timeout_seconds=120,
    )

    assert result.status == "completed"
    assert result.final_output == "总结已完成。"
    assert observed_tool_counts == [0, 0]


def test_v1_loop_intercepts_hallucinated_tool_calls_when_no_tools_available(tmp_path: Path) -> None:
    repository = SQLiteMemoryRepository(tmp_path / "hallucinated-no-tools.sqlite3")
    empty_registry = ToolRegistry(workspace_root=tmp_path)

    class HallucinatedToolProvider(LLMProvider):
        def chat(self, chat_request: RunRequest) -> RunResult:
            return RunResult(
                id="hallucinated-tool-call",
                model=chat_request.model,
                reasoning_mode=chat_request.reasoning_mode,
                choices=[
                    RunChoice(
                        index=0,
                        message=ChatMessage(
                            role="assistant",
                            content=None,
                            tool_calls=[
                                ToolCall(
                                    id="fake-tool-call",
                                    function=ToolFunction(
                                        name="shell_run",
                                        arguments='{"command":"pytest -q"}',
                                    ),
                                )
                            ],
                        ),
                        finish_reason="tool_calls",
                    )
                ],
            )

    result = AgentLoop().run(
        provider=HallucinatedToolProvider(),
        model="fake-model",
        task="总结当前结果",
        system_prompt="You are helpful.",
        session_id="hallucinated-tool-session",
        tool_registry=empty_registry,
        session_memory=SessionMemory(repository),
        summary_memory=SummaryMemory(repository),
        max_steps=3,
    )

    assert result.status == "failed"
    assert "未暴露任何工具" in result.final_output
    assert result.metrics is not None
    assert result.metrics.tool_call_count == 0
    assert any(event.event_type == "tool_call_ignored" for event in result.trace)
    assert not any(event.event_type == "tool_called" for event in result.trace)


def test_v1_planner_and_runtime_minimal_regression(tmp_path: Path) -> None:
    repository = SQLiteMemoryRepository(tmp_path / "planner-runtime.sqlite3")
    tool_registry = ToolRegistry(workspace_root=tmp_path)
    _register_lightweight_tools(tool_registry)
    provider = StaticProvider(["步骤输出", "最终总结"])
    loop = AgentLoop()

    result = loop.run_with_plan(
        provider=provider,
        model="fake-model",
        task="验证 v1 的 planner 和 runtime 仍可协同工作",
        system_prompt="You are helpful.",
        session_id="planner-runtime-session",
        tool_registry=tool_registry,
        session_memory=SessionMemory(repository),
        summary_memory=SummaryMemory(repository),
        planner=SingleStepPlanner(),
        max_steps=3,
    )

    assert result.status == "completed"
    assert result.final_output == "最终总结"
    assert len(result.plan) == 1
    assert result.plan[0].status == "completed"
    assert result.plan[0].goal == "验证 v1 的 planner 和 runtime 仍可协同工作"
    assert result.step_count >= 2


def test_planstep_and_traceevent_backward_compatibility() -> None:
    step = PlanStep(
        title="旧步骤",
        description="兼容旧字段构造方式",
        tool_name="read_file",
        input_summary="some input",
        output_summary="some output",
    )
    event = TraceEvent(
        run_id="run-1",
        session_id="session-1",
        event_type="run_started",
        message="compat trace",
        payload={"ok": True},
    )

    assert step.goal == ""
    assert step.type == "general"
    assert step.suggested_agent is None
    assert step.input_requirements == []
    assert step.success_criteria == []
    assert step.tool_name == "read_file"

    assert event.actor is None
    assert event.action is None
    assert event.status is None
    assert event.input_summary is None
    assert event.output_summary is None
    assert event.parent_event_id is None
    assert event.payload["ok"] is True


def test_v1_accepts_provider_tool_calls_with_index_field(tmp_path: Path) -> None:
    class IndexedToolCallProvider(OpenAICompatibleProvider):
        def __init__(self) -> None:
            super().__init__(
                base_url="https://example.invalid",
                api_key="fake-key",
                model="fake-model",
            )
            self._call_count = 0

        def chat(self, chat_request: RunRequest) -> RunResult:
            self._call_count += 1
            if self._call_count == 1:
                return self._parse_response(
                    {
                        "id": "provider-tool-call",
                        "model": chat_request.model,
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "tool-call-1",
                                            "type": "function",
                                            "index": 0,
                                            "function": {
                                                "name": "dummy_tool",
                                                "arguments": '{"input":"hello"}',
                                            },
                                        }
                                    ],
                                },
                                "finish_reason": "tool_calls",
                            }
                        ],
                    }
                )
            serialized_messages = [message.to_provider_dict() for message in chat_request.messages]
            assistant_messages = [
                message for message in serialized_messages if message.get("role") == "assistant"
            ]
            assert assistant_messages
            assert assistant_messages[-1]["tool_calls"][0]["function"]["name"] == "dummy_tool"
            assert "index" not in assistant_messages[-1]["tool_calls"][0]
            return self._parse_response(
                {
                    "id": "provider-final-answer",
                    "model": chat_request.model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "工具调用兼容仍然正常。",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                }
            )

    repository = SQLiteMemoryRepository(tmp_path / "tool-call-memory.sqlite3")
    tool_registry = ToolRegistry(workspace_root=tmp_path)
    _register_lightweight_tools(tool_registry)
    provider = IndexedToolCallProvider()
    loop = AgentLoop()

    result = loop.run(
        provider=provider,
        model="fake-model",
        task="调用一个工具然后给出结论",
        system_prompt="You are helpful.",
        session_id="tool-call-session",
        tool_registry=tool_registry,
        session_memory=SessionMemory(repository),
        summary_memory=SummaryMemory(repository),
        max_steps=3,
    )

    assert result.status == "completed"
    assert result.final_output == "工具调用兼容仍然正常。"
    assert result.metrics is not None
    assert result.metrics.tool_call_count == 1
    assert any(event.event_type == "tool_called" for event in result.trace)


def test_v1_tools_accept_workspace_alias_paths(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "demo.txt").write_text("hello", encoding="utf-8")

    registry = ToolRegistry(workspace_root=tmp_path)
    _register_lightweight_tools(registry)

    root_result = registry.execute_tool(
        tool_name="list_dir",
        arguments={"path": "/workspace"},
        tool_call_id="alias-root",
    )
    nested_result = registry.execute_tool(
        tool_name="read_file",
        arguments={"path": "/workspace/src/demo.txt"},
        tool_call_id="alias-file",
    )

    assert root_result.is_error is False
    assert nested_result.is_error is False
    assert "demo.txt" in nested_result.content


def test_chroma_ensure_rag_collection_creates_listable_collection(tmp_path: Path) -> None:
    store = ChromaVectorStore(persist_dir=tmp_path / "chroma-rag")
    info = store.ensure_rag_collection("Product-A")
    assert info["rag_id"] == "product-a"
    assert info["collection_name"] == f"{store.default_collection_name}__product-a"
    rag_ids = {row["rag_id"] for row in store.list_rag_collections()}
    assert "product-a" in rag_ids


def test_chroma_normalize_rag_id_strips_and_lowercases(tmp_path: Path) -> None:
    store = ChromaVectorStore(persist_dir=tmp_path / "chroma-rag2")
    assert store.normalize_rag_id("  Foo Bar  ") == "foo-bar"
    assert store.normalize_rag_id(None) == "default"
    assert normalize_rag_id_value("  Foo Bar  ") == "foo-bar"


def test_strict_normalize_v2_rag_ids_rejects_accidental_default() -> None:
    with pytest.raises(RagIdValidationError, match="规范化后等同于 default"):
        strict_normalize_v2_rag_ids(rag_id="@@@", rag_ids=None)


def test_strict_normalize_v2_rag_ids_accepts_explicit_default() -> None:
    assert strict_normalize_v2_rag_ids(rag_id="default", rag_ids=None) == ["default"]
    assert strict_normalize_v2_rag_ids(rag_id="DeFaUlT", rag_ids=None) == ["default"]


def test_strict_normalize_v2_rag_ids_dedupes_by_canonical_form() -> None:
    assert strict_normalize_v2_rag_ids(rag_id="Foo Bar", rag_ids=["foo-bar"]) == ["foo-bar"]


def test_document_retriever_dedupes_rag_ids_by_canonical_form() -> None:
    retriever = object.__new__(DocumentRetriever)
    assert retriever._resolve_rag_ids(rag_id="Foo Bar", rag_ids=["foo-bar", "  Backend Java  "]) == [
        "foo-bar",
        "backend-java",
    ]


def test_retrieve_docs_tool_rejects_invalid_rag_when_multi_rag_enabled() -> None:
    class FakeRetriever:
        def retrieve(self, **_: object) -> list[dict[str, object]]:  # pragma: no cover
            raise AssertionError("should not retrieve")

    tool = RetrieveDocsTool(retriever=FakeRetriever(), allow_multi_rag=True)  # type: ignore[arg-type]
    result = tool.execute({"query": "q", "rag_id": "@@@"}, "call-invalid-rag")
    assert result.is_error is True
    payload = json.loads(result.content)
    assert "规范化后等同于 default" in str(payload.get("error", ""))


def test_debug_rag_overview_rejects_invalid_rag_id_before_vector_store() -> None:
    with pytest.raises(HTTPException) as excinfo:
        get_rag_overview(rag_id="@@@")

    assert excinfo.value.status_code == 400
    assert "规范化后等同于 default" in str(excinfo.value.detail)


def test_debug_rag_mutation_endpoints_reject_invalid_rag_id_before_side_effects() -> None:
    with pytest.raises(HTTPException) as delete_exc:
        delete_rag_source(RagDeleteSourceRequest(source="docs/a.md", rag_id="@@@"))
    with pytest.raises(HTTPException) as upload_exc:
        upload_rag_file(RagUploadRequest(filename="a.md", content_base64="SGk=", rag_id="@@@"))

    assert delete_exc.value.status_code == 400
    assert upload_exc.value.status_code == 400
    assert "规范化后等同于 default" in str(delete_exc.value.detail)
    assert "规范化后等同于 default" in str(upload_exc.value.detail)
