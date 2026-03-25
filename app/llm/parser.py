"""解析 Provider 响应的辅助函数。"""

from __future__ import annotations

from app.contracts.run import RunResult
from app.contracts.tool import ToolCall


def extract_tool_calls(response: RunResult) -> list[ToolCall]:
    """如果存在工具调用，则返回首个候选结果中的工具调用列表。"""
    if not response.choices:
        return []
    return response.choices[0].message.tool_calls


def extract_final_text(response: RunResult) -> str:
    """从首个候选结果中提取最终回答文本。"""
    if not response.choices:
        return ""

    message = response.choices[0].message
    if message.content:
        return message.content.strip()

    tool_calls = extract_tool_calls(response)
    if tool_calls:
        return ""

    return ""
