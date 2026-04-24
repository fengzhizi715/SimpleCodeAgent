"""Chroma 向量存储封装。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb

from app.core.config import BASE_DIR
from app.v1.rag.chunking import DocumentChunk


class ChromaVectorStore:
    """基于 Chroma 的持久化向量存储。"""

    def __init__(
        self,
        collection_name: str = "codeagent_docs",
        persist_dir: str | Path | None = None,
    ) -> None:
        self.persist_dir = Path(persist_dir) if persist_dir else BASE_DIR / ".chroma"
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def upsert(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> None:
        """写入或更新文档分块。"""
        if not chunks:
            return
        self.collection.upsert(
            ids=[chunk.chunk_id for chunk in chunks],
            documents=[chunk.content for chunk in chunks],
            metadatas=[
                {
                    "source": chunk.source,
                    "start_index": chunk.start_index,
                    "end_index": chunk.end_index,
                }
                for chunk in chunks
            ],
            embeddings=embeddings,
        )

    def query(self, query_embedding: list[float], top_k: int = 3) -> list[dict[str, Any]]:
        """按向量相似度检索文档片段。"""
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        rows: list[dict[str, Any]] = []
        for document, metadata, distance in zip(documents, metadatas, distances):
            score = 1.0 / (1.0 + float(distance))
            rows.append(
                {
                    "source": metadata.get("source", ""),
                    "start_index": metadata.get("start_index", 0),
                    "end_index": metadata.get("end_index", 0),
                    "content": document,
                    "distance": distance,
                    "score": score,
                }
            )
        return rows

    def inspect(self) -> dict[str, Any]:
        """返回集合概览信息（用于调试页展示）。"""
        total_chunks = int(self.collection.count())
        payload = self.collection.get(include=["metadatas"])
        metadatas = payload.get("metadatas") or []
        ids = payload.get("ids") or []

        source_to_chunks: dict[str, int] = {}
        for metadata in metadatas:
            source = ""
            if isinstance(metadata, dict):
                source = str(metadata.get("source") or "").strip()
            key = source or "(unknown)"
            source_to_chunks[key] = source_to_chunks.get(key, 0) + 1

        files = [
            {"source": source, "chunk_count": chunk_count}
            for source, chunk_count in sorted(source_to_chunks.items(), key=lambda item: (-item[1], item[0]))
        ]

        return {
            "collection_name": self.collection.name,
            "persist_dir": str(self.persist_dir),
            "total_chunks": total_chunks,
            "file_count": len(source_to_chunks),
            "sampled_chunk_count": len(ids),
            "files": files,
        }

    def delete_by_source(self, source: str) -> int:
        """按 source 删除对应分块并返回删除数量。"""
        normalized = source.strip()
        if not normalized:
            return 0

        matched = self.collection.get(where={"source": normalized}, include=[])
        ids = matched.get("ids") or []
        if not ids:
            return 0
        self.collection.delete(ids=ids)
        return len(ids)
