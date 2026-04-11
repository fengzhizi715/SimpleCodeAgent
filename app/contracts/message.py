"""消息协议定义。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.tool import ToolCall

Role = Literal["system", "user", "assistant", "tool"]


class ChatMessage(BaseModel):
    """模块间传递的标准聊天消息对象。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: Role
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)

    def to_provider_dict(self) -> dict[str, object]:
        """将消息转换为 provider 所需的载荷格式。"""
        payload = self.model_dump(exclude_none=True, exclude={"tool_calls"})
        if self.tool_calls:
            payload["tool_calls"] = [
                tool_call.to_provider_dict() for tool_call in self.tool_calls
            ]
        return payload
