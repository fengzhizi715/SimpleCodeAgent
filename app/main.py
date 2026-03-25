"""应用入口。"""

from __future__ import annotations

import argparse
import sys
from uuid import uuid4

from app.contracts.run import RunResult
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logger import setup_logger
from app.llm.client import LLMProviderError, OpenAICompatibleProvider
from app.memory.repository import SQLiteMemoryRepository
from app.memory.session_memory import SessionMemory
from app.memory.summary_memory import SummaryMemory
from app.runtime.loop import AgentLoop
from app.tools.registry import ToolRegistry

logger = setup_logger(settings.app_name, settings.log_level)


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="Simple LLM CLI")
    parser.add_argument("prompt", nargs="?", help="Prompt sent to the model.")
    parser.add_argument("--model", dest="model", default=settings.llm_model)
    parser.add_argument("--base-url", dest="base_url", default=settings.llm_base_url)
    parser.add_argument("--api-key", dest="api_key", default=settings.llm_api_key)
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
        default="",
        help="Optional session identifier for conversation memory.",
    )
    return parser


def run_chat(args: argparse.Namespace) -> RunResult:
    """执行一次 Agent 运行并返回标准化结果。"""
    if not args.prompt:
        raise AppError("Prompt is required. Example: python -m app.main 'Hello'")
    if not args.api_key:
        raise AppError("Missing API key. Set LLM_API_KEY or pass --api-key.")
    if not args.model:
        raise AppError("Missing model. Set LLM_MODEL or pass --model.")

    provider = OpenAICompatibleProvider(
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        timeout=settings.llm_timeout,
    )
    session_id = args.session_id or str(uuid4())
    tool_registry = ToolRegistry()
    tool_registry.register_default_tools()
    memory_repository = SQLiteMemoryRepository()
    session_memory = SessionMemory(memory_repository)
    summary_memory = SummaryMemory(memory_repository)
    return AgentLoop().run(
        provider=provider,
        model=args.model,
        task=args.prompt,
        system_prompt=args.system_prompt,
        session_id=session_id,
        temperature=args.temperature,
        tool_registry=tool_registry,
        session_memory=session_memory,
        summary_memory=summary_memory,
    )


def main() -> None:
    """启动命令行应用。"""
    args = build_parser().parse_args()
    logger.info(
        "Application started",
        extra={
            "app_env": settings.app_env,
            "debug": settings.debug,
        },
    )
    try:
        result = run_chat(args)
    except (AppError, LLMProviderError) as exc:
        logger.error(str(exc))
        sys.exit(1)

    logger.info(
        "Run completed: run_id=%s session_id=%s step_count=%s",
        result.run_id,
        result.session_id,
        result.step_count,
    )
    print(result.final_output)


if __name__ == "__main__":
    main()
