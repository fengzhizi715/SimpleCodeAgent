"""Embedding 调用能力。"""

from __future__ import annotations

import hashlib
import json
from math import sqrt
from urllib import error, request

from app.core.config import settings
from app.core.exceptions import AppError


class EmbeddingProvider:
    """Embedding Provider 抽象接口。"""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量生成文本向量。"""
        raise NotImplementedError


class LocalHashEmbeddings(EmbeddingProvider):
    """用于本地开发和测试的轻量哈希向量实现。"""

    def __init__(self, dimensions: int = 128) -> None:
        self.dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_single(text) for text in texts]

    def _embed_single(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign

        norm = sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class OpenAICompatibleEmbeddings(EmbeddingProvider):
    """OpenAI 兼容 Embedding 接口客户端。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.model, "input": texts}
        endpoint = f"{self.base_url}/embeddings"
        http_request = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=self.timeout) as response:
                raw_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise AppError(f"Embedding HTTP {exc.code}: {body}") from exc
        except error.URLError as exc:
            raise AppError(f"Embedding request failed: {exc.reason}") from exc

        data = json.loads(raw_body)
        return [item["embedding"] for item in data.get("data", [])]


def build_embedding_provider() -> EmbeddingProvider:
    """构建默认 Embedding Provider。"""
    embedding_model = getattr(settings, "embedding_model", "")
    embedding_key = getattr(settings, "embedding_api_key", "")
    embedding_base_url = getattr(settings, "embedding_base_url", settings.llm_base_url)

    if embedding_model and embedding_key:
        return OpenAICompatibleEmbeddings(
            base_url=embedding_base_url,
            api_key=embedding_key,
            model=embedding_model,
            timeout=settings.llm_timeout,
        )
    return LocalHashEmbeddings()
