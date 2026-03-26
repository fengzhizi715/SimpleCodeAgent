"""文档切分能力。"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict


class DocumentChunk(BaseModel):
    """单个文档分块。"""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    source: str
    content: str
    start_index: int
    end_index: int


def chunk_text(
    *,
    source: str | Path,
    text: str,
    chunk_size: int = 800,
    overlap: int = 120,
) -> list[DocumentChunk]:
    """将文本切分为带重叠窗口的多个片段。"""
    normalized_source = str(source)
    if not text.strip():
        return []

    chunks: list[DocumentChunk] = []
    start = 0
    index = 0
    step = max(1, chunk_size - overlap)

    while start < len(text):
        end = min(len(text), start + chunk_size)
        content = text[start:end].strip()
        if content:
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{normalized_source}:{index}",
                    source=normalized_source,
                    content=content,
                    start_index=start,
                    end_index=end,
                )
            )
        if end >= len(text):
            break
        start += step
        index += 1

    return chunks
