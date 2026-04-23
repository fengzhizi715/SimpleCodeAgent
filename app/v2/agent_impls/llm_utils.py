"""LLM and JSON parsing helpers for V2 agents."""

from __future__ import annotations

import json
from typing import Any

from app.contracts.message import ChatMessage
from app.contracts.run import RunRequest, RunResult
from app.v2.base import AgentContext


def extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def parse_tool_content(content: str) -> dict[str, object]:
    parsed = extract_json_object(content)
    if parsed is None:
        return {"raw": content}
    return parsed


def chat_json(
    *,
    context: AgentContext,
    system_prompt: str,
    user_prompt: str,
) -> tuple[dict[str, Any] | None, RunResult | None]:
    """Call provider and parse JSON object output."""
    try:
        result = context.provider.chat(
            RunRequest(
                messages=[
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(role="user", content=user_prompt),
                ],
                model=context.model,
                reasoning_mode=context.reasoning_mode,
                temperature=0.0,
            )
        )
    except Exception:
        return None, None
    if not result.choices:
        return None, result
    content = result.choices[0].message.content or ""
    return extract_json_object(content), result
