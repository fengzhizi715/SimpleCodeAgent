"""工具协议定义。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


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
    index: int | None = None

    def to_provider_dict(self) -> dict[str, object]:
        """将工具调用转换为 provider 所需格式。"""
        return self.model_dump(exclude_none=True, exclude={"index"})


class ToolDefinition(BaseModel):
    """发送给模型的工具定义。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str
    description: str
    input_schema: "ToolSchema" = Field(
        default_factory=lambda: ToolSchema(),
        validation_alias=AliasChoices("input_schema", "parameters"),
    )
    strict: bool = False
    type: Literal["function"] = "function"

    @property
    def parameters(self) -> dict[str, Any]:
        """兼容旧字段名，返回输入参数 schema。"""
        return self.input_schema.to_provider_dict()

    def to_provider_dict(self) -> dict[str, object]:
        """将工具定义转换为 OpenAI 兼容格式。"""
        return {
            "type": self.type,
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema.to_provider_dict(),
                "strict": self.strict,
            },
        }


class ToolSchema(BaseModel):
    """工具输入参数的结构定义。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: Literal["object"] = "object"
    properties: dict[str, Any] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)
    additional_properties: bool = Field(default=False, alias="additionalProperties")

    def to_provider_dict(self) -> dict[str, Any]:
        """转换为 OpenAI-compatible 工具参数 schema。"""
        return {
            "type": self.type,
            "properties": self.properties,
            "required": self.required,
            "additionalProperties": self.additional_properties,
        }


class ToolResult(BaseModel):
    """标准工具执行结果。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tool_call_id: str
    name: str
    content: str
    is_error: bool = False

    def to_message(self) -> "ChatMessage":
        """将工具结果转换为 `tool` 角色消息。"""
        from app.contracts.message import ChatMessage

        return ChatMessage(
            role="tool",
            content=self.content,
            name=self.name,
            tool_call_id=self.tool_call_id,
        )
