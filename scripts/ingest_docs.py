#!/usr/bin/env python
"""导入目录或单个文件到向量库。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.v1.rag.ingest import DocsIngestor


def main() -> None:
    """执行文档导入。"""
    parser = argparse.ArgumentParser(description="将文档导入 Chroma 向量库。")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--docs-dir", help="文档目录路径。默认使用 docs。")
    group.add_argument("--file", help="导入单个文件的绝对路径。")
    args = parser.parse_args()

    ingestor = DocsIngestor()
    if args.file:
        chunk_count = ingestor.ingest_file(args.file)
    else:
        chunk_count = ingestor.ingest_directory(args.docs_dir or "docs")
    print(f"ingested_chunks={chunk_count}")


if __name__ == "__main__":
    main()
