#!/usr/bin/env python
"""面向开发与演示的命令行入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.cli.entry import build_cli_parser, print_run_result, run_agent_task
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logger import configure_logging, get_logger
from app.llm.client import LLMProviderError

configure_logging(settings.log_level)
logger = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数。"""
    return build_cli_parser(
        description="运行一次 CodeAgent 任务。",
        task_argument_name="task",
        task_argument_help="要执行的任务描述。",
        include_trace=True,
    )


def main() -> None:
    """CLI 主入口。"""
    parser = build_parser()
    args = parser.parse_args()

    try:
        result, version, session_id, trace_lines = run_agent_task(
            task=args.task,
            version=args.version,
            model=args.model,
            reasoning_mode=args.reasoning_mode,
            base_url=args.base_url,
            api_key=args.api_key,
            service_token=args.service_token,
            system_prompt=args.system_prompt,
            temperature=args.temperature,
            session_id=args.session_id,
            workdir=args.workdir,
            max_steps=args.max_steps,
            include_trace=args.trace,
        )
    except (AppError, LLMProviderError) as exc:
        logger.exception("CLI task failed: %s", exc)
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)

    logger.info(
        "CLI task completed: version=%s run_id=%s session_id=%s trace_lines=%s",
        version,
        result.run_id,
        session_id,
        len(trace_lines),
    )
    print_run_result(result=result, version=version, session_id=session_id, trace_lines=trace_lines)


if __name__ == "__main__":
    main()
