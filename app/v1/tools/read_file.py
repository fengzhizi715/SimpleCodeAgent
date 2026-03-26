"""读取文件工具。"""

from __future__ import annotations

from app.contracts.tool import ToolDefinition, ToolResult
from app.v1.tools.base import Tool


class ReadFileTool(Tool):
    """读取文本文件，并支持长度限制。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_file",
            description="Read text content from a file inside the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file."},
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum number of characters to return.",
                        "default": 4000,
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            strict=True,
        )

    def execute(self, arguments: dict[str, object], tool_call_id: str) -> ToolResult:
        raw_path = str(arguments.get("path", ""))
        max_chars = int(arguments.get("max_chars", 4000))
        path = self.resolve_path(raw_path)
        if not path.exists():
            return self.error(
                tool_call_id=tool_call_id,
                message=f"File not found: {raw_path}",
                path=str(path),
            )
        if not path.is_file():
            return self.error(
                tool_call_id=tool_call_id,
                message=f"Path is not a file: {raw_path}",
                path=str(path),
            )

        content = path.read_text(encoding="utf-8", errors="replace")
        truncated = len(content) > max_chars
        visible_content = content[:max_chars]
        return self.success(
            tool_call_id=tool_call_id,
            content={
                "ok": True,
                "path": str(path),
                "truncated": truncated,
                "returned_chars": len(visible_content),
                "content": visible_content,
            },
        )
