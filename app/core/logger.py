"""日志配置。"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Final

from app.core.config import BASE_DIR

DEFAULT_LOG_FORMAT: Final[str] = (
    "%(asctime)s | %(levelname)s | %(name)s | run_id=%(run_id)s | session_id=%(session_id)s | %(message)s"
)
DEFAULT_DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"
DEFAULT_LOG_CONTEXT_VALUE: Final[str] = "-"
LOG_DIR: Final[Path] = BASE_DIR / "logs"
LOG_FILE: Final[Path] = LOG_DIR / "app.log"
LOG_RETENTION_DAYS: Final[int] = 30

_current_run_id: ContextVar[str] = ContextVar("current_run_id", default=DEFAULT_LOG_CONTEXT_VALUE)
_current_session_id: ContextVar[str] = ContextVar("current_session_id", default=DEFAULT_LOG_CONTEXT_VALUE)


class LogContextFilter(logging.Filter):
    """将当前执行上下文中的 run_id 和 session_id 注入日志记录。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "run_id"):
            record.run_id = _current_run_id.get()
        if not hasattr(record, "session_id"):
            record.session_id = _current_session_id.get()
        return True


def _normalize_level(level: str | int) -> int:
    """将字符串或整数日志级别转换为 logging 可识别的级别值。"""
    if isinstance(level, int):
        return level
    return getattr(logging, str(level).upper(), logging.INFO)


def configure_logging(level: str = "INFO") -> None:
    """配置应用级根日志，保证不同模块共享统一输出格式。"""
    root_logger = logging.getLogger()
    normalized_level = _normalize_level(level)
    formatter = logging.Formatter(
        fmt=DEFAULT_LOG_FORMAT,
        datefmt=DEFAULT_DATE_FORMAT,
    )
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if root_logger.handlers:
        root_logger.setLevel(normalized_level)
        for handler in root_logger.handlers:
            handler.setLevel(normalized_level)
            handler.setFormatter(formatter)
            if not any(isinstance(filter_, LogContextFilter) for filter_ in handler.filters):
                handler.addFilter(LogContextFilter())
        if not any(isinstance(handler, TimedRotatingFileHandler) for handler in root_logger.handlers):
            root_logger.addHandler(_build_file_handler(normalized_level, formatter))
        return

    root_logger.setLevel(normalized_level)
    root_logger.addHandler(_build_stream_handler(normalized_level, formatter))
    root_logger.addHandler(_build_file_handler(normalized_level, formatter))


def _build_stream_handler(level: int, formatter: logging.Formatter) -> logging.Handler:
    """创建控制台日志处理器。"""
    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(formatter)
    handler.addFilter(LogContextFilter())
    return handler


def _build_file_handler(level: int, formatter: logging.Formatter) -> logging.Handler:
    """创建按天滚动并保留最近 30 天的文件日志处理器。"""
    handler = TimedRotatingFileHandler(
        filename=str(LOG_FILE),
        when="midnight",
        interval=1,
        backupCount=LOG_RETENTION_DAYS,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(formatter)
    handler.addFilter(LogContextFilter())
    return handler


def get_logger(name: str, level: str | None = None) -> logging.Logger:
    """返回统一格式的模块级日志记录器。"""
    if level is not None:
        configure_logging(level)
    logger = logging.getLogger(name)
    if level is not None:
        logger.setLevel(_normalize_level(level))
    return logger


def setup_logger(name: str, level: str = "INFO") -> logging.Logger:
    """兼容旧调用方式，内部转为统一根日志配置。"""
    configure_logging(level)
    return get_logger(name)


def set_log_context(*, run_id: str | None = None, session_id: str | None = None) -> tuple[Token[str] | None, Token[str] | None]:
    """设置当前日志上下文，返回可用于恢复的 token。"""
    run_token: Token[str] | None = None
    session_token: Token[str] | None = None
    if run_id is not None:
        run_token = _current_run_id.set(run_id or DEFAULT_LOG_CONTEXT_VALUE)
    if session_id is not None:
        session_token = _current_session_id.set(session_id or DEFAULT_LOG_CONTEXT_VALUE)
    return run_token, session_token


def reset_log_context(run_token: Token[str] | None, session_token: Token[str] | None) -> None:
    """恢复之前的日志上下文。"""
    if run_token is not None:
        _current_run_id.reset(run_token)
    if session_token is not None:
        _current_session_id.reset(session_token)


@contextmanager
def log_context(*, run_id: str | None = None, session_id: str | None = None):
    """在一个作用域内临时注入 run_id 和 session_id 到日志上下文。"""
    run_token, session_token = set_log_context(run_id=run_id, session_id=session_id)
    try:
        yield
    finally:
        reset_log_context(run_token, session_token)
