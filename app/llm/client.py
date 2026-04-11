"""LLM Provider 接口与 OpenAI 兼容实现。"""

from __future__ import annotations

import http.client
import json
from abc import ABC, abstractmethod
from typing import Mapping
from urllib import error, request

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.contracts.message import ChatMessage
from app.contracts.run import RunRequest, RunResult, RunUsage
from app.contracts.tool import ToolCall, ToolFunction
from app.core.exceptions import AppError
from app.core.logger import get_logger

logger = get_logger(__name__)


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
        service_token: str = "",
        auth_mode: str = "auto",
        reasoning_param_style: str = "none",
        extra_headers: Mapping[str, str] | None = None,
        timeout: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.service_token = service_token
        self.auth_mode = auth_mode.lower()
        self.reasoning_param_style = reasoning_param_style.lower()
        self.extra_headers = dict(extra_headers or {})
        self.timeout = timeout

    def chat(self, chat_request: RunRequest) -> RunResult:
        payload = chat_request.to_provider_payload(fallback_model=self.model)
        payload = self._apply_reasoning_mapping(payload, chat_request.reasoning_mode)

        endpoint = f"{self.base_url}/chat/completions"
        logger.info(
            "Sending LLM request: model=%s endpoint=%s message_count=%s tool_count=%s timeout=%ss auth_mode=%s reasoning_mode=%s",
            payload.get("model", self.model),
            endpoint,
            len(chat_request.messages),
            len(chat_request.tools),
            self.timeout,
            self.auth_mode,
            chat_request.reasoning_mode,
        )
        http_request = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._build_headers(),
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=self.timeout) as response:
                response_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            logger.error("LLM provider returned HTTP error: status=%s body=%s", exc.code, body)
            raise LLMProviderError(
                f"Provider returned HTTP {exc.code}: {body}"
            ) from exc
        except error.URLError as exc:
            logger.error("LLM provider request failed: reason=%s", exc.reason)
            raise LLMProviderError(f"Provider request failed: {exc.reason}") from exc
        except (http.client.HTTPException, OSError) as exc:
            logger.error("LLM provider connection failed: error=%s", exc)
            raise LLMProviderError(f"Provider connection failed: {exc}") from exc

        try:
            data = json.loads(response_body)
        except json.JSONDecodeError as exc:
            logger.error("LLM provider returned invalid JSON response.")
            raise LLMProviderError("Provider returned invalid JSON") from exc

        return self._parse_response(data)

    def _apply_reasoning_mapping(
        self,
        payload: dict[str, object],
        reasoning_mode: str,
    ) -> dict[str, object]:
        """按 Provider 配置将 reasoning_mode 映射到实际请求字段。"""
        if reasoning_mode == "default" or self.reasoning_param_style == "none":
            return payload

        updated_payload = dict(payload)
        if self.reasoning_param_style == "reasoning_effort":
            updated_payload["reasoning_effort"] = reasoning_mode
        elif self.reasoning_param_style == "reasoning_object":
            updated_payload["reasoning"] = {"effort": reasoning_mode}
        else:
            logger.warning(
                "Unknown reasoning parameter style: style=%s; skip provider mapping.",
                self.reasoning_param_style,
            )
            return payload

        logger.info(
            "Applied provider reasoning mapping: style=%s reasoning_mode=%s",
            self.reasoning_param_style,
            reasoning_mode,
        )
        return updated_payload

    def _build_headers(self) -> dict[str, str]:
        """构造请求头，兼容 Bearer 与 Service Token 两种鉴权方式。"""
        headers = {
            "Content-Type": "application/json",
            **self.extra_headers,
        }
        headers.update(self._build_auth_headers())
        return headers

    def _build_auth_headers(self) -> dict[str, str]:
        """按鉴权模式生成认证头。"""
        if self.auth_mode == "service_token":
            if not self.service_token:
                raise LLMProviderError("Auth mode 'service_token' requires a service token.")
            return {"X-Service-Token": self.service_token}

        if self.auth_mode == "bearer":
            if not self.api_key:
                raise LLMProviderError("Auth mode 'bearer' requires an API key.")
            return {"Authorization": f"Bearer {self.api_key}"}

        if self.auth_mode == "none":
            return {}

        if self.service_token:
            return {"X-Service-Token": self.service_token}
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}

    def _parse_response(self, payload: dict[str, object]) -> RunResult:
        try:
            parsed = ProviderResponsePayload.model_validate(payload)
        except ValidationError as exc:
            logger.error("LLM provider response validation failed: %s", exc)
            raise LLMProviderError(f"Provider response validation failed: {exc}") from exc

        logger.info(
            "Received LLM response: model=%s choices=%s usage_total_tokens=%s",
            parsed.model or self.model,
            len(parsed.choices),
            parsed.usage.total_tokens if parsed.usage is not None else 0,
        )

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
                        "message": ChatMessage.model_validate(choice.message.model_dump()),
                        "finish_reason": choice.finish_reason,
                    }
                    for choice in parsed.choices
                ],
                "usage": usage,
            }
        )
