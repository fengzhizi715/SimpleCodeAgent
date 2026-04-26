"""文档检索能力。"""

from __future__ import annotations

import re

from app.v1.rag.embeddings import EmbeddingProvider, build_embedding_provider
from app.v1.rag.vector_store import ChromaVectorStore, normalize_rag_id_value


class DocumentRetriever:
    """按查询文本检索相关文档片段。"""

    def __init__(
        self,
        vector_store: ChromaVectorStore | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.vector_store = vector_store or ChromaVectorStore()
        self.embedding_provider = embedding_provider or build_embedding_provider()

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        min_score: float = 0.0,
        rerank: bool = True,
        fetch_k: int | None = None,
        rag_id: str | None = None,
        rag_ids: list[str] | None = None,
    ) -> list[dict[str, object]]:
        """返回与查询最相关的文档片段。"""
        query_embedding = self.embedding_provider.embed_texts([query])[0]
        candidate_count = fetch_k if fetch_k is not None else max(top_k * 3, top_k)
        resolved_rag_ids = self._resolve_rag_ids(rag_id=rag_id, rag_ids=rag_ids)
        matches: list[dict[str, object]] = []
        for item in resolved_rag_ids:
            matches.extend(
                self.vector_store.query(
                    query_embedding=query_embedding,
                    top_k=candidate_count,
                    rag_id=item,
                )
            )
        filtered_matches = [
            match
            for match in matches
            if float(match.get("score", 0.0)) >= min_score
        ]
        if not rerank:
            return filtered_matches[:top_k]

        query_terms = self._extract_terms(query)
        reranked_matches = []
        for match in filtered_matches:
            content = str(match.get("content", ""))
            lexical_score = self._lexical_score(query_terms, content)
            vector_score = float(match.get("score", 0.0))
            rerank_score = (vector_score * 0.7) + (lexical_score * 0.3)
            reranked_matches.append(
                {
                    **match,
                    "lexical_score": lexical_score,
                    "rerank_score": rerank_score,
                }
            )

        reranked_matches.sort(
            key=lambda item: (float(item.get("rerank_score", 0.0)), float(item.get("score", 0.0))),
            reverse=True,
        )
        return reranked_matches[:top_k]

    def _resolve_rag_ids(self, *, rag_id: str | None, rag_ids: list[str] | None) -> list[str]:
        values: list[str] = []
        if isinstance(rag_ids, list):
            values.extend(str(item).strip() for item in rag_ids)
        if rag_id is not None:
            values.append(str(rag_id).strip())
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            key = normalize_rag_id_value(value)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(key)
        if normalized:
            return normalized
        return ["default"]

    def _extract_terms(self, text: str) -> set[str]:
        """从查询中提取可用于轻量重排的词项。"""
        return {
            token
            for token in re.findall(r"[A-Za-z0-9_]+", text.lower())
            if len(token) >= 2
        }

    def _lexical_score(self, query_terms: set[str], content: str) -> float:
        """基于词项重合度计算轻量 lexical 分数。"""
        if not query_terms:
            return 0.0
        content_terms = set(re.findall(r"[A-Za-z0-9_]+", content.lower()))
        if not content_terms:
            return 0.0
        overlap = len(query_terms & content_terms)
        return overlap / len(query_terms)
