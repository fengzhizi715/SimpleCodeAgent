"""追加文件工具。"""

from __future__ import annotations

from app.contracts.tool import ToolDefinition, ToolResult
from app.v1.tools.base import Tool


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
        existed_before = path.exists()
        previous_content = path.read_text(encoding="utf-8", errors="replace") if existed_before and path.is_file() else ""
        updated_content = f"{previous_content}{content}"
        diff_payload = self.build_diff_preview(path=path, before=previous_content, after=updated_content)
        if dry_run:
            return self.success(
                tool_call_id=tool_call_id,
                content={
                    "ok": True,
                    "path": str(path),
                    "dry_run": True,
                    "created": not existed_before,
                    "bytes": len(content.encode("utf-8")),
                    **diff_payload,
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
                "created": not existed_before,
                "bytes": len(content.encode("utf-8")),
                **diff_payload,
            },
        )
