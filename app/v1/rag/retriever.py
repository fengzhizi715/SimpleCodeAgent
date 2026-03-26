"""文档检索能力。"""

from __future__ import annotations

from pathlib import Path

from app.v1.rag.embeddings import EmbeddingProvider, build_embedding_provider
from app.v1.rag.vector_store import ChromaVectorStore


class DocumentRetriever:
    """按查询文本检索相关文档片段。"""

    def __init__(
        self,
        vector_store: ChromaVectorStore | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.vector_store = vector_store or ChromaVectorStore()
        self.embedding_provider = embedding_provider or build_embedding_provider()

    def retrieve(self, query: str, top_k: int = 3) -> list[dict[str, object]]:
        """返回与查询最相关的文档片段。"""
        query_embedding = self.embedding_provider.embed_texts([query])[0]
        return self.vector_store.query(query_embedding=query_embedding, top_k=top_k)
