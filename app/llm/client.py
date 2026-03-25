"""LLM Provider 接口与 OpenAI 兼容实现。"""

from __future__ import annotations

import http.client
import json
from abc import ABC, abstractmethod
from urllib import error, request

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.contracts.message import Message
from app.contracts.run import RunRequest, RunResult, RunUsage
from app.contracts.tool import ToolCall, ToolFunction
from app.core.exceptions import AppError


class ProviderMessagePayload(BaseModel):
    """OpenAI 兼容响应中的消息载荷。"""

    model_config = ConfigDict(extra="ignore")

    role: str = "assistant"
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)


class ProviderChoicePayload(BaseModel):
    """OpenAI 兼容响应中的候选结果载荷。"""

    model_config = ConfigDict(extra="ignore")

    index: int = 0
    message: ProviderMessagePayload
    finish_reason: str | None = None


class ProviderUsagePayload(BaseModel):
    """OpenAI 兼容响应中的使用量载荷。"""

    model_config = ConfigDict(extra="ignore")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ProviderResponsePayload(BaseModel):
    """OpenAI 兼容响应的外层结构。"""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    model: str = ""
    choices: list[ProviderChoicePayload] = Field(default_factory=list)
    usage: ProviderUsagePayload | None = None


class LLMProvider(ABC):
    """聊天补全 Provider 的抽象接口。"""

    @abstractmethod
    def chat(self, chat_request: RunRequest) -> RunResult:
        """执行一次聊天补全请求。"""


class LLMProviderError(AppError):
    """当 Provider 调用失败时抛出。"""


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI 兼容聊天补全接口客户端。"""

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

    def chat(self, chat_request: RunRequest) -> RunResult:
        payload = chat_request.to_provider_payload(fallback_model=self.model)

        endpoint = f"{self.base_url}/chat/completions"
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
                response_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise LLMProviderError(
                f"Provider returned HTTP {exc.code}: {body}"
            ) from exc
        except error.URLError as exc:
            raise LLMProviderError(f"Provider request failed: {exc.reason}") from exc
        except (http.client.HTTPException, OSError) as exc:
            raise LLMProviderError(f"Provider connection failed: {exc}") from exc

        try:
            data = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise LLMProviderError("Provider returned invalid JSON") from exc

        return self._parse_response(data)

    def _parse_response(self, payload: dict[str, object]) -> RunResult:
        try:
            parsed = ProviderResponsePayload.model_validate(payload)
        except ValidationError as exc:
            raise LLMProviderError(f"Provider response validation failed: {exc}") from exc

        usage = None
        if parsed.usage is not None:
            usage = RunUsage.model_validate(parsed.usage.model_dump())

        return RunResult.model_validate(
            {
                "id": parsed.id,
                "model": parsed.model or self.model,
                "choices": [
                    {
                        "index": choice.index,
                        "message": Message.model_validate(choice.message.model_dump()),
                        "finish_reason": choice.finish_reason,
                    }
                    for choice in parsed.choices
                ],
                "usage": usage,
            }
        )
