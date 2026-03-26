#!/usr/bin/env python
"""导入 docs 目录到向量库。"""

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
    parser = argparse.ArgumentParser(description="将 docs 目录导入 Chroma 向量库。")
    parser.add_argument("--docs-dir", default="docs", help="文档目录路径。")
    args = parser.parse_args()

    ingestor = DocsIngestor()
    chunk_count = ingestor.ingest_directory(args.docs_dir)
    print(f"ingested_chunks={chunk_count}")


if __name__ == "__main__":
    main()
