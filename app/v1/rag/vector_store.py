"""Chroma 向量存储封装。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb

from app.core.config import BASE_DIR
from app.v1.rag.chunking import DocumentChunk


def normalize_rag_id_value(rag_id: str | None) -> str:
    """将用户输入的 rag_id 规范化为内部标识（与 Chroma 集合命名规则一致）。"""
    raw = str(rag_id or "").strip().lower()
    if not raw:
        return "default"
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in raw)
    safe = safe.strip("-_")
    return safe or "default"


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
        self.default_collection_name = collection_name
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def upsert(self, chunks: list[DocumentChunk], embeddings: list[list[float]], rag_id: str | None = None) -> None:
        """写入或更新文档分块。"""
        if not chunks:
            return
        collection = self._collection_for_rag_id(rag_id)
        collection.upsert(
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

    def query(
        self,
        query_embedding: list[float],
        top_k: int = 3,
        rag_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """按向量相似度检索文档片段。"""
        collection = self._collection_for_rag_id(rag_id)
        resolved_rag_id = self._normalize_rag_id(rag_id)
        result = collection.query(
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
                    "rag_id": resolved_rag_id,
                }
            )
        return rows

    def inspect(self, rag_id: str | None = None) -> dict[str, Any]:
        """返回集合概览信息（用于调试页展示）。"""
        collection = self._collection_for_rag_id(rag_id)
        total_chunks = int(collection.count())
        payload = collection.get(include=["metadatas"])
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
            "collection_name": collection.name,
            "rag_id": self._normalize_rag_id(rag_id),
            "persist_dir": str(self.persist_dir),
            "total_chunks": total_chunks,
            "file_count": len(source_to_chunks),
            "sampled_chunk_count": len(ids),
            "files": files,
        }

    def delete_by_source(self, source: str, rag_id: str | None = None) -> int:
        """按 source 删除对应分块并返回删除数量。"""
        normalized = source.strip()
        if not normalized:
            return 0

        collection = self._collection_for_rag_id(rag_id)
        matched = collection.get(where={"source": normalized}, include=[])
        ids = matched.get("ids") or []
        if not ids:
            return 0
        collection.delete(ids=ids)
        return len(ids)

    def ensure_rag_collection(self, rag_id: str | None) -> dict[str, Any]:
        """确保指定 rag_id 对应的 Chroma 集合已存在（无文档的空集合也可被列出）。"""
        normalized = self._normalize_rag_id(rag_id)
        collection = self._collection_for_rag_id(rag_id)
        return {"rag_id": normalized, "collection_name": collection.name}

    def delete_rag_collection(self, rag_id: str | None) -> dict[str, Any]:
        """删除指定 RAG 集合；default 集合不允许通过该方法删除。"""
        normalized = self._normalize_rag_id(rag_id)
        if normalized == "default":
            raise ValueError("default 知识库不允许删除。")
        collection_name = self.resolve_collection_name(normalized)
        existing = {str(getattr(item, "name", "") or "") for item in self.client.list_collections()}
        if collection_name not in existing:
            raise KeyError(f"知识库不存在: {normalized}")
        self.client.delete_collection(name=collection_name)
        return {"rag_id": normalized, "collection_name": collection_name}

    def list_rag_collections(self) -> list[dict[str, Any]]:
        """列出当前持久化目录中的全部 RAG 集合。"""
        rows: list[dict[str, Any]] = []
        default_name = self.default_collection_name
        try:
            collections = list(self.client.list_collections())
        except Exception:
            collections = []
        for item in collections:
            name = str(getattr(item, "name", "") or "")
            if not name:
                continue
            if name == default_name:
                rag_id = "default"
            elif name.startswith(f"{default_name}__"):
                rag_id = name[len(default_name) + 2 :] or "default"
            else:
                # 兼容历史/外部创建的集合名，直接把名字视为 rag_id。
                rag_id = name
            rows.append({"rag_id": rag_id, "collection_name": name})
        rows.sort(key=lambda row: (row["rag_id"] != "default", row["rag_id"]))
        return rows

    def _collection_for_rag_id(self, rag_id: str | None):
        collection_name = self.resolve_collection_name(rag_id)
        return self.client.get_or_create_collection(name=collection_name)

    def resolve_collection_name(self, rag_id: str | None) -> str:
        normalized = self._normalize_rag_id(rag_id)
        if normalized == "default":
            return self.default_collection_name
        return f"{self.default_collection_name}__{normalized}"

    def normalize_rag_id(self, rag_id: str | None) -> str:
        """将用户输入的 rag_id 规范化为内部标识（与集合命名规则一致）。"""
        return normalize_rag_id_value(rag_id)

    def _normalize_rag_id(self, rag_id: str | None) -> str:
        return normalize_rag_id_value(rag_id)
