"""文档导入流程。"""

from __future__ import annotations

from pathlib import Path

from app.core.config import BASE_DIR
from app.v1.rag.chunking import DocumentChunk, chunk_text
from app.v1.rag.embeddings import EmbeddingProvider, build_embedding_provider
from app.v1.rag.vector_store import ChromaVectorStore


class DocsIngestor:
    """将 docs 目录文档导入向量库。"""

    def __init__(
        self,
        vector_store: ChromaVectorStore | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.vector_store = vector_store or ChromaVectorStore()
        self.embedding_provider = embedding_provider or build_embedding_provider()

    def ingest_directory(self, docs_dir: str | Path | None = None) -> int:
        """导入目录下全部文档并返回分块数量。"""
        root = (Path(docs_dir) if docs_dir else BASE_DIR / "docs").resolve()
        files = [
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".md", ".txt", ".py"}
        ]
        all_chunks: list[DocumentChunk] = []
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            try:
                source = path.relative_to(BASE_DIR.resolve())
            except ValueError:
                source = path.name
            all_chunks.extend(chunk_text(source=source, text=text))

        if not all_chunks:
            return 0

        embeddings = self.embedding_provider.embed_texts([chunk.content for chunk in all_chunks])
        self.vector_store.upsert(all_chunks, embeddings)
        return len(all_chunks)
