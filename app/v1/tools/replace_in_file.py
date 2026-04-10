"""文件内容替换工具。"""

from __future__ import annotations

from app.contracts.tool import ToolDefinition, ToolResult
from app.v1.tools.base import Tool


class ReplaceInFileTool(Tool):
    """替换文件中的指定文本。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="replace_in_file",
            description="Replace text in an existing file.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path."},
                    "old_text": {"type": "string", "description": "Text to replace."},
                    "new_text": {"type": "string", "description": "Replacement text."},
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, only report the change.",
                        "default": False,
                    },
                },
                "required": ["path", "old_text", "new_text"],
                "additionalProperties": False,
            },
            strict=True,
        )

    def execute(self, arguments: dict[str, object], tool_call_id: str) -> ToolResult:
        raw_path = str(arguments.get("path", ""))
        old_text = str(arguments.get("old_text", ""))
        new_text = str(arguments.get("new_text", ""))
        dry_run = bool(arguments.get("dry_run", False))
        path = self.resolve_path(raw_path)
        if not path.exists() or not path.is_file():
            return self.error(
                tool_call_id=tool_call_id,
                message=f"File not found: {raw_path}",
                path=str(path),
            )

        content = path.read_text(encoding="utf-8", errors="replace")
        occurrences = content.count(old_text)
        if occurrences == 0:
            return self.error(
                tool_call_id=tool_call_id,
                message="Target text not found.",
                path=str(path),
            )

        updated = content.replace(old_text, new_text)
        diff_payload = self.build_diff_preview(path=path, before=content, after=updated)
        if not dry_run:
            path.write_text(updated, encoding="utf-8")
        return self.success(
            tool_call_id=tool_call_id,
            content={
                "ok": True,
                "path": str(path),
                "replacements": occurrences,
                "dry_run": dry_run,
                **diff_payload,
            },
        )
