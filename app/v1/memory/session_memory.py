"""会话记忆管理。"""

from __future__ import annotations

from app.contracts.message import ChatMessage
from app.v1.memory.base import MemoryRepository


class SessionMemory:
    """读取并持久化最近几轮会话历史。"""

    def __init__(self, repository: MemoryRepository, history_limit: int = 6) -> None:
        self.repository = repository
        self.history_limit = history_limit

    def load(self, session_id: str) -> list[ChatMessage]:
        """读取会话最近的消息。"""
        return self.repository.get_session_messages(session_id=session_id, limit=self.history_limit)

    def append(self, session_id: str, messages: list[ChatMessage]) -> None:
        """持久化会话消息。"""
        self.repository.append_session_messages(session_id=session_id, messages=messages)
