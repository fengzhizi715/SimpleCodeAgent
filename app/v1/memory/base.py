"""Memory 接口定义。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.contracts.message import ChatMessage


class MemoryRepository(ABC):
    """记忆存储的抽象持久化接口。"""

    @abstractmethod
    def get_session_messages(self, session_id: str, limit: int) -> list[ChatMessage]:
        """读取某个会话最近的消息。"""

    @abstractmethod
    def append_session_messages(self, session_id: str, messages: list[ChatMessage]) -> None:
        """持久化某个会话的消息。"""

    @abstractmethod
    def get_summary(self, session_id: str) -> str | None:
        """读取某个会话的摘要记忆。"""

    @abstractmethod
    def save_summary(self, session_id: str, summary: str) -> None:
        """持久化某个会话的摘要记忆。"""

    def cleanup_old_sessions(self, max_age_days: int = 30) -> int:
        """清理超过指定天数的会话及其关联数据。

        默认实现为空操作，子类可覆盖以实现具体清理逻辑。

        Args:
            max_age_days: 保留最近多少天的会话，默认 30 天。

        Returns:
            被清理的会话数量。
        """
        return 0
