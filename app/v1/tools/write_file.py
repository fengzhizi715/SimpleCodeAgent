"""写入文件工具。"""

from __future__ import annotations

from app.contracts.tool import ToolDefinition, ToolResult
from app.v1.tools.base import Tool


class WriteFileTool(Tool):
    """创建或覆盖写入文件。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="write_file",
            description="Create or overwrite a file in the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file."},
                    "content": {"type": "string", "description": "Full file content to write."},
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, do not actually write the file.",
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
        diff_payload = self.build_diff_preview(path=path, before=previous_content, after=content)

        if dry_run:
            return self.success(
                tool_call_id=tool_call_id,
                content={
                    "ok": True,
                    "dry_run": True,
                    "path": str(path),
                    "created": not existed_before,
                    "bytes": len(content.encode("utf-8")),
                    **diff_payload,
                },
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return self.success(
            tool_call_id=tool_call_id,
            content={
                "ok": True,
                "dry_run": False,
                "path": str(path),
                "created": not existed_before,
                "bytes": len(content.encode("utf-8")),
                **diff_payload,
            },
        )
