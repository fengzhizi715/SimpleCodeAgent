"""摘要记忆占位实现。"""

from __future__ import annotations

from app.v1.memory.base import MemoryRepository


class SummaryMemory:
    """为后续长程摘要记忆预留的接口。"""

    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    def get(self, session_id: str) -> str | None:
        """读取会话摘要。"""
        return self.repository.get_summary(session_id)

    def save(self, session_id: str, summary: str) -> None:
        """保存会话摘要。"""
        self.repository.save_summary(session_id, summary)
