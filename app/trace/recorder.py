"""JSONL Trace 记录器（辅助 debug 日志，非权威数据源）。"""

from __future__ import annotations

import json
from pathlib import Path

from app.contracts.trace import TraceEvent
from app.core.config import BASE_DIR
from app.core.logger import get_logger

logger = get_logger(__name__)


class JsonlTraceRecorder:
    """将 Trace 事件追加写入 JSONL 文件。

    JSONL 是辅助 debug 日志，SQLite 才是权威数据源。
    JSONL 写入失败不应影响运行流程，仅记录警告日志。
    """

    def __init__(self, run_id: str, trace_dir: str | Path | None = None) -> None:
        self.trace_dir = Path(trace_dir) if trace_dir else BASE_DIR / ".traces"
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.trace_dir / f"{run_id}.jsonl"

    def record(self, event: TraceEvent) -> None:
        """追加写入单个 Trace 事件。写入失败时仅记录警告，不抛异常。"""
        try:
            with self.file_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")
        except OSError:
            logger.warning("JSONL trace write failed: file=%s", self.file_path)

    def record_many(self, events: list[TraceEvent]) -> None:
        """追加写入多个 Trace 事件。写入失败时仅记录警告，不抛异常。"""
        if not events:
            return
        try:
            with self.file_path.open("a", encoding="utf-8") as file:
                for event in events:
                    file.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")
        except OSError:
            logger.warning("JSONL trace write failed: file=%s", self.file_path)
