"""运行协议定义。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.message import Message
from app.contracts.tool import ToolDefinition
from app.contracts.trace import TraceEvent


class RunRequest(BaseModel):
    """单次模型调用的标准请求。"""

    model_config = ConfigDict(extra="forbid")

    messages: list[Message]
    model: str
    temperature: float = 0.0
    max_tokens: int | None = None
    tools: list[ToolDefinition] = Field(default_factory=list)

    def to_provider_payload(self, fallback_model: str | None = None) -> dict[str, object]:
        """将请求转换为 OpenAI 兼容格式的载荷。"""
        payload: dict[str, object] = {
            "model": self.model or fallback_model,
            "messages": [message.to_provider_dict() for message in self.messages],
            "temperature": self.temperature,
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        if self.tools:
            payload["tools"] = [tool.to_provider_dict() for tool in self.tools]
        return payload


class RunChoice(BaseModel):
    """一次模型输出中的一个候选结果。"""

    model_config = ConfigDict(extra="forbid")

    index: int
    message: Message
    finish_reason: str | None = None


class RunUsage(BaseModel):
    """Token 使用统计信息。"""

    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class RunResult(BaseModel):
    """单次模型调用的标准结果。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    model: str
    choices: list[RunChoice]
    usage: RunUsage | None = None
    run_id: str | None = None
    session_id: str | None = None
    step_count: int = 0
    status: Literal["completed", "failed", "max_steps_exceeded"] | None = None
    final_output: str = ""
    trace: list[TraceEvent] = Field(default_factory=list)
