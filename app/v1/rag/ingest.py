"""文档导入流程。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.core.config import BASE_DIR
from app.v1.rag.chunking import DocumentChunk, chunk_text
from app.v1.rag.embeddings import EmbeddingProvider, build_embedding_provider
from app.v1.rag.vector_store import ChromaVectorStore

SupportedReader = Callable[[Path], str]


class DocsIngestor:
    """将 docs 目录文档导入向量库。"""

    def __init__(
        self,
        vector_store: ChromaVectorStore | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.vector_store = vector_store or ChromaVectorStore()
        self.embedding_provider = embedding_provider or build_embedding_provider()
        self._readers: dict[str, SupportedReader] = {
            ".docx": self._read_docx,
            ".md": self._read_plain_text,
            ".pdf": self._read_pdf,
            ".py": self._read_plain_text,
            ".txt": self._read_plain_text,
        }

    def ingest_directory(self, docs_dir: str | Path | None = None) -> int:
        """导入目录下全部文档并返回分块数量。"""
        root = (Path(docs_dir) if docs_dir else BASE_DIR / "docs").resolve()
        files = [
            path
            for path in root.rglob("*")
            if path.is_file() and self._is_supported_file(path)
        ]
        all_chunks = self._build_chunks(files)

        if not all_chunks:
            return 0

        embeddings = self.embedding_provider.embed_texts([chunk.content for chunk in all_chunks])
        self.vector_store.upsert(all_chunks, embeddings)
        return len(all_chunks)

    def ingest_file(self, file_path: str | Path) -> int:
        """导入单个文件并返回分块数量。"""
        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"文件不存在: {path}")
        if not self._is_supported_file(path):
            raise ValueError("不支持的文件类型，仅支持: .txt, .md, .py, .pdf, .docx")

        all_chunks = self._build_chunks([path])
        if not all_chunks:
            return 0

        embeddings = self.embedding_provider.embed_texts([chunk.content for chunk in all_chunks])
        self.vector_store.upsert(all_chunks, embeddings)
        return len(all_chunks)

    def _build_chunks(self, files: list[Path]) -> list[DocumentChunk]:
        """读取文件并构建文本分块。"""
        all_chunks: list[DocumentChunk] = []
        for path in files:
            text = self._read_file(path)
            if not text.strip():
                continue
            try:
                source = path.relative_to(BASE_DIR.resolve())
            except ValueError:
                source = path.name
            all_chunks.extend(chunk_text(source=source, text=text))
        return all_chunks

    def _is_supported_file(self, path: Path) -> bool:
        """判断当前文件是否支持导入。"""
        return path.suffix.lower() in self._readers

    def _read_file(self, path: Path) -> str:
        """根据文件类型读取文本内容。"""
        suffix = path.suffix.lower()
        reader = self._readers.get(suffix)
        if reader is None:
            raise ValueError(f"不支持的文件类型: {suffix}")
        return reader(path)

    def _read_plain_text(self, path: Path) -> str:
        """读取普通文本文件。"""
        return path.read_text(encoding="utf-8", errors="replace")

    def _read_pdf(self, path: Path) -> str:
        """提取 PDF 中的文本内容。"""
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("缺少 pypdf 依赖，无法导入 PDF 文件。") from exc

        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)

    def _read_docx(self, path: Path) -> str:
        """提取 DOCX 中的文本内容。"""
        try:
            from docx import Document
        except ImportError as exc:
            raise RuntimeError("缺少 python-docx 依赖，无法导入 DOCX 文件。") from exc

        document = Document(str(path))
        paragraphs = [paragraph.text for paragraph in document.paragraphs]
        return "\n".join(paragraphs)
