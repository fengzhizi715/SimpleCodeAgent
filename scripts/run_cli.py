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
from app.core.logger import configure_logging, get_logger, log_context
from app.llm.client import LLMProviderError, OpenAICompatibleProvider
from app.trace.repository import SQLiteTraceRepository
from app.v1.memory.repository import SQLiteMemoryRepository
from app.v1.memory.session_memory import SessionMemory
from app.v1.memory.summary_memory import SummaryMemory
from app.v1.planner.simple_planner import SimplePlanner
from app.v1.runtime.loop import AgentLoop
from app.v1.tools.registry import ToolRegistry

configure_logging(settings.log_level)
logger = get_logger(__name__)


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
    parser.add_argument(
        "--session-id",
        default=settings.session_id,
        help="可选会话 ID，用于连续对话。未传时默认读取 SESSION_ID。",
    )
    parser.add_argument(
        "--project-root",
        default=settings.workspace_root,
        help="目标项目根目录。未传时默认使用当前仓库；设置 WORKSPACE_ROOT 也可生效。",
    )
    parser.add_argument("--model", default=settings.llm_model, help="模型名称。")
    parser.add_argument("--base-url", default=settings.llm_base_url, help="LLM 服务地址。")
    parser.add_argument("--api-key", default=settings.llm_api_key, help="LLM API Key。")
    parser.add_argument("--service-token", default=settings.llm_service_token, help="Service Token。")
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


def run_task(args: argparse.Namespace) -> tuple[str, str, str, list[str], str]:
    """执行任务并返回答案、run_id、session_id、简版 trace 和版本。"""
    if not args.model:
        raise AppError("缺少模型名，请设置 LLM_MODEL 或传入 --model。")
    if not (args.api_key or args.service_token):
        raise AppError("缺少鉴权信息，请设置 LLM_API_KEY / LLM_SERVICE_TOKEN，或传入 --api-key / --service-token。")
    version = _ensure_supported_version(args.version)

    provider = OpenAICompatibleProvider(
        base_url=args.base_url,
        api_key=args.api_key,
        service_token=args.service_token,
        auth_mode=settings.llm_auth_mode,
        model=args.model,
        timeout=settings.llm_timeout,
    )
    session_id = args.session_id or str(uuid4())
    with log_context(session_id=session_id):
        logger.info(
            "Preparing CLI task run: version=%s model=%s project_root=%s trace=%s",
            version,
            args.model,
            args.project_root or "<current-repo>",
            args.trace,
        )
        repository = SQLiteMemoryRepository()
        session_memory = SessionMemory(repository)
        summary_memory = SummaryMemory(repository)
        tool_registry = ToolRegistry(workspace_root=args.project_root or None)
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

        return result.final_output, result.run_id or "", result.session_id or session_id, trace_lines, version


def main() -> None:
    """CLI 主入口。"""
    parser = build_parser()
    args = parser.parse_args()

    try:
        answer, run_id, session_id, trace_lines, version = run_task(args)
    except (AppError, LLMProviderError) as exc:
        logger.exception("CLI task failed: %s", exc)
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)

    logger.info(
        "CLI task completed: version=%s run_id=%s session_id=%s trace_lines=%s",
        version,
        run_id,
        session_id,
        len(trace_lines),
    )

    print("Answer:")
    print(answer)
    print()
    print(f"Version: {version}")
    print()
    print(f"Run ID: {run_id}")
    print(f"Session ID: {session_id}")

    if trace_lines:
        print()
        print("Trace:")
        for line in trace_lines:
            print(f"- {line}")


if __name__ == "__main__":
    main()
