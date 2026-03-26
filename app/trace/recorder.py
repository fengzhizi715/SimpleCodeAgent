"""JSONL Trace 记录器。"""

from __future__ import annotations

import json
from pathlib import Path

from app.contracts.trace import TraceEvent
from app.core.config import BASE_DIR


class JsonlTraceRecorder:
    """将 Trace 事件写入 JSONL 文件。"""

    def __init__(self, run_id: str, trace_dir: str | Path | None = None) -> None:
        self.trace_dir = Path(trace_dir) if trace_dir else BASE_DIR / ".traces"
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.trace_dir / f"{run_id}.jsonl"

    def record(self, event: TraceEvent) -> None:
        """追加写入单个 Trace 事件。"""
        with self.file_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")

    def record_many(self, events: list[TraceEvent]) -> None:
        """追加写入多个 Trace 事件。"""
        if not events:
            return
        with self.file_path.open("a", encoding="utf-8") as file:
            for event in events:
                file.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")
