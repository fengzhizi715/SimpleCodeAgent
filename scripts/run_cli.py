#!/usr/bin/env python
"""面向开发与演示的命令行入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Literal
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.core.exceptions import AppError, UnsupportedAgentVersionError
from app.llm.client import LLMProviderError, OpenAICompatibleProvider
from app.trace.repository import SQLiteTraceRepository
from app.v1.memory.repository import SQLiteMemoryRepository
from app.v1.memory.session_memory import SessionMemory
from app.v1.memory.summary_memory import SummaryMemory
from app.v1.planner.simple_planner import SimplePlanner
from app.v1.runtime.loop import AgentLoop
from app.v1.tools.registry import ToolRegistry


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数。"""
    parser = argparse.ArgumentParser(description="运行一次 CodeAgent 任务。")
    parser.add_argument("task", help="要执行的任务描述。")
    parser.add_argument(
        "--version",
        choices=["v1", "v2"],
        default="v1",
        help="选择 Agent 版本。",
    )
    parser.add_argument("--session-id", default="", help="可选会话 ID，用于连续对话。")
    parser.add_argument("--model", default=settings.llm_model, help="模型名称。")
    parser.add_argument("--base-url", default=settings.llm_base_url, help="LLM 服务地址。")
    parser.add_argument("--api-key", default=settings.llm_api_key, help="LLM API Key。")
    parser.add_argument(
        "--system",
        dest="system_prompt",
        default="You are a helpful assistant.",
        help="系统提示词。",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="采样温度。",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="输出简版 Trace 时间线。",
    )
    return parser


def _ensure_supported_version(version: str) -> Literal["v1"]:
    """校验当前 CLI 支持的 Agent 版本。"""
    if version == "v1":
        return "v1"
    if version == "v2":
        raise UnsupportedAgentVersionError("v2 入口已预留，但当前尚未实现。")
    raise UnsupportedAgentVersionError(f"不支持的 Agent 版本：{version}")


def run_task(args: argparse.Namespace) -> tuple[str, str, list[str], str]:
    """执行任务并返回答案、run_id、简版 trace 和版本。"""
    if not args.api_key:
        raise AppError("缺少 API Key，请设置 LLM_API_KEY 或传入 --api-key。")
    if not args.model:
        raise AppError("缺少模型名，请设置 LLM_MODEL 或传入 --model。")
    version = _ensure_supported_version(args.version)

    provider = OpenAICompatibleProvider(
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        timeout=settings.llm_timeout,
    )
    session_id = args.session_id or str(uuid4())
    repository = SQLiteMemoryRepository()
    session_memory = SessionMemory(repository)
    summary_memory = SummaryMemory(repository)
    tool_registry = ToolRegistry()
    tool_registry.register_default_tools()
    planner = SimplePlanner()
    loop = AgentLoop()

    if planner.should_plan(args.task):
        result = loop.run_with_plan(
            provider=provider,
            model=args.model,
            task=args.task,
            system_prompt=args.system_prompt,
            session_id=session_id,
            temperature=args.temperature,
            tool_registry=tool_registry,
            session_memory=session_memory,
            summary_memory=summary_memory,
            planner=planner,
        )
    else:
        result = loop.run(
            provider=provider,
            model=args.model,
            task=args.task,
            system_prompt=args.system_prompt,
            session_id=session_id,
            temperature=args.temperature,
            tool_registry=tool_registry,
            session_memory=session_memory,
            summary_memory=summary_memory,
        )

    trace_lines: list[str] = []
    if args.trace and result.run_id:
        trace_repo = SQLiteTraceRepository(repository.db)
        events = trace_repo.query_timeline(result.run_id)
        trace_lines = [
            f"{event.event_type}: {event.message}"
            for event in events
        ]

    return result.final_output, result.run_id or "", trace_lines, version


def main() -> None:
    """CLI 主入口。"""
    parser = build_parser()
    args = parser.parse_args()

    try:
        answer, run_id, trace_lines, version = run_task(args)
    except (AppError, LLMProviderError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)

    print("Answer:")
    print(answer)
    print()
    print(f"Version: {version}")
    print()
    print(f"Run ID: {run_id}")

    if trace_lines:
        print()
        print("Trace:")
        for line in trace_lines:
            print(f"- {line}")


if __name__ == "__main__":
    main()
