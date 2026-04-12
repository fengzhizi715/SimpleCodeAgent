"""工具注册与路由。"""

from __future__ import annotations
from pathlib import Path
from typing import Any

from app.contracts.tool import ToolCall, ToolDefinition, ToolResult
from app.core.logger import get_logger
from app.v1.tools.append_file import AppendFileTool
from app.v1.tools.base import DummyTool, Tool
from app.v1.tools.file_search import FileSearchTool
from app.v1.tools.list_dir import ListDirTool
from app.v1.tools.multi_file_patch import MultiFilePatchTool
from app.v1.tools.read_file import ReadFileTool
from app.v1.tools.retrieve_docs import RetrieveDocsTool
from app.v1.tools.replace_in_file import ReplaceInFileTool
from app.v1.tools.router import ToolRouter
from app.v1.tools.shell_run import ShellRunTool
from app.v1.tools.write_file import WriteFileTool

logger = get_logger(__name__)


class ToolRegistry:
    """用于工具定义注册和调用路由的注册表。"""

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        self.workspace_root = Path(workspace_root).expanduser().resolve() if workspace_root else None
        self._router = ToolRouter(self)

    def register(self, tool: Tool) -> None:
        """按工具定义中的名称注册工具实例。"""
        self._tools[tool.definition.name] = tool
        logger.info("Registered tool: tool=%s workspace_root=%s", tool.definition.name, self.workspace_root or "<current-repo>")

    def register_dummy_tool(self) -> None:
        """注册默认 dummy 工具。"""
        self.register(DummyTool(workspace_root=self.workspace_root))

    def register_default_tools(self) -> None:
        """注册标准工作区工具集。"""
        # v1 默认工具集强调“小范围可验证编程任务”：
        # 先观察，再修改，最后验证，而不是直接做高风险外部动作。
        self.register_dummy_tool()
        self.register(ReadFileTool(workspace_root=self.workspace_root))
        self.register(FileSearchTool(workspace_root=self.workspace_root))
        self.register(WriteFileTool(workspace_root=self.workspace_root))
        self.register(ShellRunTool(workspace_root=self.workspace_root))
        self.register(ListDirTool(workspace_root=self.workspace_root))
        self.register(ReplaceInFileTool(workspace_root=self.workspace_root))
        self.register(AppendFileTool(workspace_root=self.workspace_root))
        self.register(MultiFilePatchTool(workspace_root=self.workspace_root))
        self.register(RetrieveDocsTool(workspace_root=self.workspace_root))

    def get_tool_definitions(self) -> list[ToolDefinition]:
        """返回暴露给 LLM 的全部工具定义。"""
        return [tool.definition for tool in self._tools.values()]

    def get(self, tool_name: str) -> Tool | None:
        """根据工具名获取已注册工具。"""
        return self._tools.get(tool_name)

    def execute_tool(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        tool_call_id: str = "direct-tool-call",
    ) -> ToolResult:
        """按工具名直接执行工具，供 runtime 的确定性步骤使用。"""
        return self._router.route(
            tool_name,
            arguments,
            tool_call_id=tool_call_id,
        )

    def execute_tool_call(self, tool_call: ToolCall) -> ToolResult:
        """将工具调用路由到正确工具并执行。"""
        return self._router.route_tool_call(tool_call)
