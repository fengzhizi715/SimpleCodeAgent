"""工具路由与执行。"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from app.contracts.tool import ToolCall, ToolResult
from app.core.logger import get_logger

if TYPE_CHECKING:
    from app.v1.tools.base import Tool
    from app.v1.tools.registry import ToolRegistry

logger = get_logger(__name__)


class ToolRouter:
    """根据工具名将调用分发到已注册工具。"""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def route(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        tool_call_id: str = "direct-tool-call",
    ) -> ToolResult:
        """按工具名直接执行工具。"""
        tool = self.registry.get(tool_name)
        if tool is None:
            logger.error("Direct tool routing failed: tool=%s reason=not_found", tool_name)
            return self._build_error_result(
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                message=f"Tool not found: {tool_name}",
            )

        try:
            return tool.execute(arguments=arguments, tool_call_id=tool_call_id)
        except Exception as exc:
            logger.exception("Direct tool routing failed: tool=%s error=%s", tool_name, exc)
            return self._build_error_result(
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                message=f"Tool execution failed for {tool_name}: {exc}",
            )

    def route_tool_call(self, tool_call: ToolCall) -> ToolResult:
        """将模型返回的 ToolCall 路由到目标工具。"""
        tool_name = tool_call.function.name
        tool = self.registry.get(tool_name)
        if tool is None:
            logger.error("Tool routing failed: tool=%s reason=not_found", tool_name)
            return self._build_error_result(
                tool_name=tool_name,
                tool_call_id=tool_call.id,
                message=f"Tool not found: {tool_name}",
            )

        arguments = self._load_arguments(tool_call)
        if isinstance(arguments, ToolResult):
            return arguments

        try:
            return tool.execute(arguments=arguments, tool_call_id=tool_call.id)
        except Exception as exc:
            logger.exception("Tool routing failed: tool=%s error=%s", tool_name, exc)
            return self._build_error_result(
                tool_name=tool_name,
                tool_call_id=tool_call.id,
                message=f"Tool execution failed for {tool_name}: {exc}",
            )

    def _load_arguments(self, tool_call: ToolCall) -> dict[str, Any] | ToolResult:
        """解析模型返回的 JSON 参数。"""
        tool_name = tool_call.function.name
        try:
            arguments = json.loads(tool_call.function.arguments or "{}")
        except json.JSONDecodeError:
            logger.error("Tool routing failed: tool=%s reason=invalid_json_arguments", tool_name)
            return self._build_error_result(
                tool_name=tool_name,
                tool_call_id=tool_call.id,
                message=f"Invalid tool arguments for {tool_name}",
                raw_arguments=tool_call.function.arguments,
            )

        if not isinstance(arguments, dict):
            logger.error("Tool routing failed: tool=%s reason=arguments_not_object", tool_name)
            return self._build_error_result(
                tool_name=tool_name,
                tool_call_id=tool_call.id,
                message=f"Tool arguments must be a JSON object for {tool_name}",
            )
        return arguments

    def _build_error_result(
        self,
        *,
        tool_name: str,
        tool_call_id: str,
        message: str,
        **extra: Any,
    ) -> ToolResult:
        """构造统一的工具错误结果。"""
        payload: dict[str, Any] = {
            "ok": False,
            "error": message,
            "tool_name": tool_name,
        }
        payload.update(extra)
        return ToolResult(
            tool_call_id=tool_call_id,
            name=tool_name,
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            is_error=True,
        )
