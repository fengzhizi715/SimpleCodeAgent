"""应用入口。"""

from __future__ import annotations

import argparse
import sys
from typing import Literal
from uuid import uuid4

from app.contracts.run import RunResult
from app.core.config import settings
from app.core.exceptions import AppError, UnsupportedAgentVersionError
from app.core.logger import configure_logging, get_logger, log_context
from app.llm.client import LLMProviderError, OpenAICompatibleProvider
from app.v1.memory.repository import SQLiteMemoryRepository
from app.v1.memory.session_memory import SessionMemory
from app.v1.memory.summary_memory import SummaryMemory
from app.v1.planner.simple_planner import SimplePlanner
from app.v1.runtime.loop import AgentLoop
from app.v1.tools.registry import ToolRegistry

configure_logging(settings.log_level)
logger = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="Simple LLM CLI")
    parser.add_argument("prompt", nargs="?", help="Prompt sent to the model.")
    parser.add_argument("--version", dest="version", choices=["v1", "v2"], default="v1")
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
        help="Target workdir for tool execution. Defaults to current repo or WORKDIR/WORKSPACE_ROOT when set.",
    )
    parser.add_argument(
        "--max-steps",
        dest="max_steps",
        type=int,
        default=3,
        help="Maximum execution steps.",
    )
    return parser


def _ensure_supported_version(version: str) -> Literal["v1"]:
    """校验当前 CLI 支持的 Agent 版本。"""
    if version == "v1":
        return "v1"
    if version == "v2":
        raise UnsupportedAgentVersionError("v2 入口已预留，但当前尚未实现。")
    raise UnsupportedAgentVersionError(f"不支持的 Agent 版本：{version}")


def run_chat(args: argparse.Namespace) -> RunResult:
    """执行一次 Agent 运行并返回标准化结果。"""
    if not args.prompt:
        raise AppError("Prompt is required. Example: python -m app.main 'Hello'")
    if not args.model:
        raise AppError("Missing model. Set LLM_MODEL or pass --model.")
    if not (args.api_key or args.service_token):
        raise AppError("Missing auth credentials. Set LLM_API_KEY / LLM_SERVICE_TOKEN or pass --api-key / --service-token.")
    _ensure_supported_version(args.version)

    provider = OpenAICompatibleProvider(
        base_url=args.base_url,
        api_key=args.api_key,
        service_token=args.service_token,
        auth_mode=settings.llm_auth_mode,
        reasoning_param_style=settings.llm_reasoning_param_style,
        model=args.model,
        timeout=settings.llm_timeout,
    )
    session_id = args.session_id or str(uuid4())
    with log_context(session_id=session_id):
        logger.info(
            "Preparing agent run: version=%s model=%s workdir=%s max_steps=%s reasoning_mode=%s",
            args.version,
            args.model,
            args.workdir or "<current-repo>",
            args.max_steps,
            args.reasoning_mode,
        )
        tool_registry = ToolRegistry(workspace_root=args.workdir or None)
        tool_registry.register_default_tools()
        memory_repository = SQLiteMemoryRepository()
        session_memory = SessionMemory(memory_repository)
        summary_memory = SummaryMemory(memory_repository)
        loop = AgentLoop()
        planner = SimplePlanner()
        if planner.should_plan(args.prompt):
            return loop.run_with_plan(
                provider=provider,
                model=args.model,
                task=args.prompt,
                system_prompt=args.system_prompt,
                session_id=session_id,
                reasoning_mode=args.reasoning_mode,
                temperature=args.temperature,
                max_steps=args.max_steps,
                tool_registry=tool_registry,
                session_memory=session_memory,
                summary_memory=summary_memory,
                planner=planner,
            )
        return loop.run(
            provider=provider,
            model=args.model,
            task=args.prompt,
            system_prompt=args.system_prompt,
            session_id=session_id,
            reasoning_mode=args.reasoning_mode,
            temperature=args.temperature,
            max_steps=args.max_steps,
            tool_registry=tool_registry,
            session_memory=session_memory,
            summary_memory=summary_memory,
        )


def main() -> None:
    """启动命令行应用。"""
    args = build_parser().parse_args()
    logger.info(
        "Application started: app_env=%s debug=%s log_level=%s",
        settings.app_env,
        settings.debug,
        settings.log_level,
    )
    try:
        result = run_chat(args)
    except (AppError, LLMProviderError) as exc:
        logger.exception("Application failed: %s", exc)
        sys.exit(1)

    logger.info(
        "Run completed: version=%s run_id=%s session_id=%s step_count=%s",
        args.version,
        result.run_id,
        result.session_id,
        result.step_count,
    )
    print("Answer:")
    print(result.final_output)
    print()
    print(f"Version: {args.version}")
    print(f"Reasoning Mode: {result.reasoning_mode}")
    print()
    print(f"Run ID: {result.run_id or ''}")
    print(f"Session ID: {result.session_id or args.session_id or ''}")
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


if __name__ == "__main__":
    main()
