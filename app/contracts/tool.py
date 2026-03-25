"""工具协议定义。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolFunction(BaseModel):
    """工具调用中的函数载荷。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str
    arguments: str = "{}"


class ToolCall(BaseModel):
    """由模型产出的工具调用。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str
    type: Literal["function"] = "function"
    function: ToolFunction

    def to_provider_dict(self) -> dict[str, object]:
        """将工具调用转换为 provider 所需格式。"""
        return self.model_dump()


class ToolDefinition(BaseModel):
    """发送给模型的工具定义。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    strict: bool = False
    type: Literal["function"] = "function"

    def to_provider_dict(self) -> dict[str, object]:
        """将工具定义转换为 OpenAI 兼容格式。"""
        return {
            "type": self.type,
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
                "strict": self.strict,
            },
        }


class ToolResult(BaseModel):
    """标准工具执行结果。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tool_call_id: str
    name: str
    content: str
    is_error: bool = False

    def to_message(self) -> "Message":
        """将工具结果转换为 `tool` 角色消息。"""
        from app.contracts.message import Message

        return Message(
            role="tool",
            content=self.content,
            name=self.name,
            tool_call_id=self.tool_call_id,
        )
