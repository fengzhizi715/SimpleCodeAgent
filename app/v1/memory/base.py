"""Memory 接口定义。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.contracts.message import Message


class MemoryRepository(ABC):
    """记忆存储的抽象持久化接口。"""

    @abstractmethod
    def get_session_messages(self, session_id: str, limit: int) -> list[Message]:
        """读取某个会话最近的消息。"""

    @abstractmethod
    def append_session_messages(self, session_id: str, messages: list[Message]) -> None:
        """持久化某个会话的消息。"""

    @abstractmethod
    def get_summary(self, session_id: str) -> str | None:
        """读取某个会话的摘要记忆。"""

    @abstractmethod
    def save_summary(self, session_id: str, summary: str) -> None:
        """持久化某个会话的摘要记忆。"""
