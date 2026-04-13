"""应用入口。"""

from __future__ import annotations

import argparse
import sys

from app.cli.entry import build_cli_parser, print_run_result, run_agent_task
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logger import configure_logging, get_logger
from app.llm.client import LLMProviderError

configure_logging(settings.log_level)
logger = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    return build_cli_parser(
        description="Simple LLM CLI",
        task_argument_name="prompt",
        task_argument_help="Prompt sent to the model.",
        task_optional=True,
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
        result, version, session_id, trace_lines = run_agent_task(
            task=args.prompt or "",
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
            include_trace=False,
        )
    except (AppError, LLMProviderError) as exc:
        logger.exception("Application failed: %s", exc)
        sys.exit(1)

    logger.info(
        "Run completed: version=%s run_id=%s session_id=%s step_count=%s",
        version,
        result.run_id,
        result.session_id,
        result.step_count,
    )
    print_run_result(result=result, version=version, session_id=session_id, trace_lines=trace_lines)


if __name__ == "__main__":
    main()
