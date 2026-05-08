"""CLI 共享运行逻辑。"""

from __future__ import annotations

import argparse
import asyncio
from typing import Literal
from uuid import uuid4

from app.core.config import settings
from app.core.exceptions import AppError, RagIdValidationError, UnsupportedAgentVersionError
from app.core.logger import get_logger, log_context
from app.core.session import derive_project_session_id
from app.llm.client import OpenAICompatibleProvider
from app.trace.repository import SQLiteTraceRepository
from app.v1.memory.repository import SQLiteMemoryRepository
from app.v1.memory.session_memory import SessionMemory
from app.v1.memory.summary_memory import SummaryMemory
from app.v1.planner.simple_planner import SimplePlanner
from app.v1.runtime.loop import AgentLoop
from app.v1.tools.registry import ToolRegistry
from app.v2.agent_impls import describe_agent_matrix
from app.v2.factory import build_orchestrator_runtime
from app.v3.runner import format_v3_result, run_v3

logger = get_logger(__name__)


def build_cli_parser(
    *,
    description: str,
    task_argument_name: str,
    task_argument_help: str,
    task_optional: bool = False,
    include_trace: bool = False,
) -> argparse.ArgumentParser:
    """构建统一的 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(task_argument_name, nargs="?" if task_optional else None, help=task_argument_help)
    parser.add_argument("--version", dest="version", choices=["v1", "v2", "v3"], default="v1")
    parser.add_argument("--model", dest="model", default=settings.llm_model)
    parser.add_argument(
        "--reasoning-mode",
        dest="reasoning_mode",
        choices=["default", "low", "medium", "high"],
        default="default",
        help="Reasoning mode marker.",
    )
    parser.add_argument("--base-url", dest="base_url", default=settings.llm_base_url)
    parser.add_argument("--api-key", dest="api_key", default=settings.llm_api_key)
    parser.add_argument("--service-token", dest="service_token", default=settings.llm_service_token)
    parser.add_argument(
        "--system",
        dest="system_prompt",
        default="You are a helpful assistant.",
        help="Optional system prompt.",
    )
    parser.add_argument(
        "--temperature",
        dest="temperature",
        type=float,
        default=0.0,
        help="Sampling temperature.",
    )
    parser.add_argument(
        "--session-id",
        dest="session_id",
        default=settings.session_id,
        help="Optional session identifier for conversation memory. Defaults to SESSION_ID when set.",
    )
    parser.add_argument(
        "--workdir",
        "--project-root",
        dest="workdir",
        default=settings.workdir,
        help="Target workdir for tool execution. Defaults to current repo or WORKDIR when set.",
    )
    parser.add_argument(
        "--max-steps",
        dest="max_steps",
        type=int,
        default=3,
        help="Maximum execution steps.",
    )
    parser.add_argument(
        "--run-timeout-seconds",
        dest="run_timeout_seconds",
        type=int,
        default=120,
        help="Per-run timeout in seconds for v1 execution.",
    )
    if include_trace:
        parser.add_argument(
            "--trace",
            action="store_true",
            help="输出简版 Trace 时间线。",
        )
    return parser


def ensure_supported_version(version: str) -> Literal["v1", "v2", "v3"]:
    """校验当前 CLI 支持的 Agent 版本。"""
    if version == "v1":
        return "v1"
    if version == "v2":
        return "v2"
    if version == "v3":
        return "v3"
    raise UnsupportedAgentVersionError(f"不支持的 Agent 版本：{version}")


def run_agent_task(
    *,
    task: str,
    version: str,
    model: str,
    reasoning_mode: str,
    base_url: str,
    api_key: str,
    service_token: str,
    system_prompt: str,
    temperature: float,
    session_id: str,
    workdir: str,
    max_steps: int,
    run_timeout_seconds: int,
    include_trace: bool = False,
) -> tuple:
    """执行一次 Agent 任务，供多个 CLI 入口复用。"""
    if not task:
        raise AppError("Prompt is required. Example: python -m app.main 'Hello'")
    resolved_version = ensure_supported_version(version)

    if resolved_version == "v3":
        result = asyncio.run(
            run_v3(
                goal=task,
                workdir=workdir or ".",
                include_events=include_trace,
                include_trace=include_trace,
            )
        )
        report = result["report"]
        return (
            result,
            resolved_version,
            "",
            [f"{item.get('event_type')}: {item.get('message')}" for item in result["trace"]] if include_trace else [],
        )

    if not model:
        raise AppError("Missing model. Set LLM_MODEL or pass --model.")
    if not (api_key or service_token):
        raise AppError("Missing auth credentials. Set LLM_API_KEY / LLM_SERVICE_TOKEN or pass --api-key / --service-token.")

    provider = OpenAICompatibleProvider(
        base_url=base_url,
        api_key=api_key,
        service_token=service_token,
        auth_mode=settings.llm_auth_mode,
        reasoning_param_style=settings.llm_reasoning_param_style,
        model=model,
        timeout=settings.llm_timeout,
    )
    resolved_session_id = derive_project_session_id(session_id or str(uuid4()), workdir)
    with log_context(session_id=resolved_session_id):
        logger.info(
            "Preparing agent run: version=%s model=%s workdir=%s max_steps=%s reasoning_mode=%s include_trace=%s",
            resolved_version,
            model,
            workdir or "<current-repo>",
            max_steps,
            reasoning_mode,
            include_trace,
        )
        repository = SQLiteMemoryRepository()
        tool_registry = ToolRegistry(workspace_root=workdir or None)
        tool_registry.register_default_tools(multi_rag=(resolved_version == "v2"))
        if resolved_version == "v2":
            runtime = build_orchestrator_runtime(SQLiteTraceRepository(repository.db))
            try:
                result = runtime.run(
                    provider=provider,
                    model=model,
                    task=task,
                    session_id=resolved_session_id,
                    tool_registry=tool_registry,
                    workspace_root=workdir or ".",
                    reasoning_mode=reasoning_mode,
                    max_steps=max_steps,
                )
            except RagIdValidationError as exc:
                raise AppError(str(exc)) from exc
        else:
            session_memory = SessionMemory(repository)
            summary_memory = SummaryMemory(repository)
            planner = SimplePlanner()
            loop = AgentLoop()

            if planner.should_plan(task):
                result = loop.run_with_plan(
                    provider=provider,
                    model=model,
                    task=task,
                    system_prompt=system_prompt,
                    session_id=resolved_session_id,
                    reasoning_mode=reasoning_mode,
                    temperature=temperature,
                    max_steps=max_steps,
                    run_timeout_seconds=run_timeout_seconds,
                    tool_registry=tool_registry,
                    session_memory=session_memory,
                    summary_memory=summary_memory,
                    planner=planner,
                )
            else:
                result = loop.run(
                    provider=provider,
                    model=model,
                    task=task,
                    system_prompt=system_prompt,
                    session_id=resolved_session_id,
                    reasoning_mode=reasoning_mode,
                    temperature=temperature,
                    max_steps=max_steps,
                    run_timeout_seconds=run_timeout_seconds,
                    tool_registry=tool_registry,
                    session_memory=session_memory,
                    summary_memory=summary_memory,
                )

        # 与 API 路径保持一致：v1 规划执行会产生多个内部子 run，
        # CLI 也需要用用户原始 task 再落一条顶层 run，供 /history 展示。
        if resolved_version == "v1" and result.run_id and result.session_id:
            repository.save_run(
                result,
                task,
                workdir=workdir or None,
                is_top_level=True,
                parent_run_id=None,
            )

        trace_lines: list[str] = []
        if include_trace and result.run_id:
            trace_repo = SQLiteTraceRepository(repository.db)
            events = trace_repo.query_timeline(result.run_id)
            trace_lines = [f"{event.event_type}: {event.message}" for event in events]

        return (
            result,
            resolved_version,
            resolved_session_id,
            trace_lines,
        )


def print_run_result(
    *,
    result,
    version: str,
    session_id: str,
    trace_lines: list[str] | None = None,
) -> None:
    """统一输出运行结果。"""
    if version == "v3":
        report = result["report"]
        print(
            format_v3_result(
                report=report,
                planning=result.get("planning"),
                inspection=result.get("inspection"),
                events=result.get("events"),
                trace=result.get("trace"),
            )
        )
        return
    print("Answer:")
    print(result.final_output)
    print()
    print(f"Version: {version}")
    print(f"Reasoning Mode: {result.reasoning_mode}")
    print(f"Direct Tool Execution Used: {'yes' if result.direct_tool_execution_used else 'no'}")
    print()
    print(f"Run ID: {result.run_id or ''}")
    print(f"Session ID: {result.session_id or session_id or ''}")
    if result.usage is not None:
        print(
            "Usage: "
            f"prompt={result.usage.prompt_tokens} completion={result.usage.completion_tokens} total={result.usage.total_tokens}"
        )
    if result.metrics is not None:
        print(
            "Metrics: "
            f"duration={result.metrics.duration_seconds:.2f}s "
            f"llm_calls={result.metrics.llm_call_count} "
            f"tool_calls={result.metrics.tool_call_count} "
            f"tool_errors={result.metrics.tool_error_count} "
            f"memory_writes={result.metrics.memory_write_count} "
            f"fallbacks={result.metrics.fallback_count}"
        )
    if trace_lines:
        print()
        print("Trace:")
        for line in trace_lines:
            print(f"- {line}")


def print_agent_matrix() -> None:
    """输出当前 V2 默认 Agent 角色矩阵，供 debug/教学展示。"""
    rows = describe_agent_matrix()
    print("Agent Matrix:")
    for row in rows:
        capabilities = ", ".join(str(item) for item in row["capabilities"])
        print(
            f"- {row['agent_id']} ({row['class_name']}): "
            f"role={row['role']} availability={row['availability']} "
            f"capabilities=[{capabilities}]"
        )
