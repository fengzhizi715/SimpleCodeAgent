"""工具注册与路由。"""

from __future__ import annotations

import json
from typing import Any

from app.contracts.tool import ToolCall, ToolDefinition, ToolResult
from app.tools.append_file import AppendFileTool
from app.tools.base import DummyTool, Tool
from app.tools.file_search import FileSearchTool
from app.tools.list_dir import ListDirTool
from app.tools.read_file import ReadFileTool
from app.tools.replace_in_file import ReplaceInFileTool
from app.tools.shell_run import ShellRunTool
from app.tools.write_file import WriteFileTool


class ToolRegistry:
    """用于工具定义注册和调用路由的注册表。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """按工具定义中的名称注册工具实例。"""
        self._tools[tool.definition.name] = tool

    def register_dummy_tool(self) -> None:
        """注册默认 dummy 工具。"""
        self.register(DummyTool())

    def register_default_tools(self) -> None:
        """注册标准工作区工具集。"""
        self.register_dummy_tool()
        self.register(ReadFileTool())
        self.register(FileSearchTool())
        self.register(WriteFileTool())
        self.register(ShellRunTool())
        self.register(ListDirTool())
        self.register(ReplaceInFileTool())
        self.register(AppendFileTool())

    def get_tool_definitions(self) -> list[ToolDefinition]:
        """返回暴露给 LLM 的全部工具定义。"""
        return [tool.definition for tool in self._tools.values()]

    def execute_tool_call(self, tool_call: ToolCall) -> ToolResult:
        """将工具调用路由到正确工具并执行。"""
        tool_name = tool_call.function.name
        tool = self._tools.get(tool_name)
        if tool is None:
            return self._error_result(
                tool_call=tool_call,
                message=f"Tool not found: {tool_name}",
            )

        try:
            arguments = json.loads(tool_call.function.arguments or "{}")
        except json.JSONDecodeError:
            return self._error_result(
                tool_call=tool_call,
                message=f"Invalid tool arguments for {tool_name}",
                raw_arguments=tool_call.function.arguments,
            )

        if not isinstance(arguments, dict):
            return self._error_result(
                tool_call=tool_call,
                message=f"Tool arguments must be a JSON object for {tool_name}",
            )

        try:
            return tool.execute(arguments=arguments, tool_call_id=tool_call.id)
        except Exception as exc:
            return self._error_result(
                tool_call=tool_call,
                message=f"Tool execution failed for {tool_name}: {exc}",
            )

    def _error_result(
        self,
        *,
        tool_call: ToolCall,
        message: str,
        **extra: Any,
    ) -> ToolResult:
        """创建结构化的工具错误结果。"""
        payload: dict[str, Any] = {
            "ok": False,
            "error": message,
            "tool_name": tool_call.function.name,
        }
        payload.update(extra)
        return ToolResult(
            tool_call_id=tool_call.id,
            name=tool_call.function.name,
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            is_error=True,
        )
