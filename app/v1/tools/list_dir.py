"""目录列举工具。"""

from __future__ import annotations

from app.contracts.tool import ToolDefinition, ToolResult
from app.v1.tools.base import Tool


class ListDirTool(Tool):
    """列出工作区内某个目录的内容。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list_dir",
            description="List files and directories inside a workspace directory.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path.", "default": "."},
                    "max_entries": {
                        "type": "integer",
                        "description": "Maximum number of entries to return.",
                        "default": 100,
                    },
                },
                "additionalProperties": False,
            },
            strict=True,
        )

    def execute(self, arguments: dict[str, object], tool_call_id: str) -> ToolResult:
        raw_path = str(arguments.get("path", "."))
        max_entries = int(arguments.get("max_entries", 100))
        path = self.resolve_path(raw_path)
        if not path.exists() or not path.is_dir():
            return self.error(
                tool_call_id=tool_call_id,
                message=f"Directory not found: {raw_path}",
                path=str(path),
            )

        entries = []
        for entry in sorted(path.iterdir(), key=lambda item: item.name)[:max_entries]:
            entries.append(
                {
                    "name": entry.name,
                    "path": str(entry),
                    "is_dir": entry.is_dir(),
                }
            )
        return self.success(
            tool_call_id=tool_call_id,
            content={
                "ok": True,
                "path": str(path),
                "entries": entries,
                "truncated": len(entries) == max_entries,
            },
        )
