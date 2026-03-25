"""追加文件工具。"""

from __future__ import annotations

from app.contracts.tool import ToolDefinition, ToolResult
from app.tools.base import Tool


class AppendFileTool(Tool):
    """向文件追加文本内容。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="append_file",
            description="Append text content to a file, creating it if needed.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path."},
                    "content": {"type": "string", "description": "Content to append."},
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, do not write the content.",
                        "default": False,
                    },
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            strict=True,
        )

    def execute(self, arguments: dict[str, object], tool_call_id: str) -> ToolResult:
        raw_path = str(arguments.get("path", ""))
        content = str(arguments.get("content", ""))
        dry_run = bool(arguments.get("dry_run", False))
        path = self.resolve_path(raw_path)
        if dry_run:
            return self.success(
                tool_call_id=tool_call_id,
                content={
                    "ok": True,
                    "path": str(path),
                    "dry_run": True,
                    "bytes": len(content.encode("utf-8")),
                },
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(content)
        return self.success(
            tool_call_id=tool_call_id,
            content={
                "ok": True,
                "path": str(path),
                "dry_run": False,
                "bytes": len(content.encode("utf-8")),
            },
        )
