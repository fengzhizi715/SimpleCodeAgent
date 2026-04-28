"""Lightweight per-RAG configuration storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import BASE_DIR


DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 120


class RagIndexConfig(BaseModel):
    """Index-time configuration for one RAG collection."""

    model_config = ConfigDict(extra="forbid")

    rag_id: str
    chunk_size: int = Field(default=DEFAULT_CHUNK_SIZE, ge=100, le=8000)
    overlap: int = Field(default=DEFAULT_CHUNK_OVERLAP, ge=0, le=4000)


class RagConfigStore:
    """Stores small RAG metadata outside Chroma."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or BASE_DIR / ".rag" / "rag_configs.json"

    def get(self, rag_id: str | None) -> RagIndexConfig:
        """Return config for a rag_id, falling back to defaults."""
        normalized = str(rag_id or "default").strip() or "default"
        raw = self._read_all().get(normalized)
        if isinstance(raw, dict):
            try:
                return RagIndexConfig.model_validate({"rag_id": normalized, **raw})
            except ValueError:
                return RagIndexConfig(rag_id=normalized)
        return RagIndexConfig(rag_id=normalized)

    def save(self, config: RagIndexConfig) -> RagIndexConfig:
        """Persist config and return the validated value."""
        if config.overlap >= config.chunk_size:
            raise ValueError("overlap 必须小于 chunk_size。")
        data = self._read_all()
        data[config.rag_id] = {
            "chunk_size": config.chunk_size,
            "overlap": config.overlap,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return config

    def delete(self, rag_id: str | None) -> bool:
        """Delete config for a rag_id if present."""
        normalized = str(rag_id or "").strip()
        if not normalized:
            return False
        data = self._read_all()
        existed = normalized in data
        if existed:
            data.pop(normalized, None)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return existed

    def _read_all(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return raw if isinstance(raw, dict) else {}
