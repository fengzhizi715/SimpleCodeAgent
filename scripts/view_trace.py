#!/usr/bin/env python
"""查看某次运行的 Trace 时间线。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.sqlite import SQLiteDB
from app.trace.repository import SQLiteTraceRepository
from app.trace.viewer import format_timeline


def main() -> None:
    """读取并打印指定 run_id 的 timeline。"""
    parser = argparse.ArgumentParser(description="查看某次运行的 Trace timeline。")
    parser.add_argument("run_id", help="目标 run_id")
    parser.add_argument("--db-path", default=None, help="可选 SQLite 文件路径")
    args = parser.parse_args()

    repository = SQLiteTraceRepository(SQLiteDB(args.db_path))
    events = repository.query_timeline(args.run_id)
    print(format_timeline(events))


if __name__ == "__main__":
    main()
