"""读取文件工具。"""

from __future__ import annotations

from app.contracts.tool import ToolDefinition, ToolResult
from app.v1.tools.base import Tool


class ReadFileTool(Tool):
    """读取文本文件，支持行号范围和长度限制。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_file",
            description="Read text content from a file inside the workspace. Supports line range selection.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file."},
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum number of characters to return.",
                        "default": 4000,
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "1-based starting line number. If omitted, reads from the beginning.",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "1-based ending line number (inclusive). If omitted, reads to the end.",
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
        raw_start_line = arguments.get("start_line")
        raw_end_line = arguments.get("end_line")
        start_line = int(raw_start_line) if raw_start_line is not None else None
        end_line = int(raw_end_line) if raw_end_line is not None else None

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

        all_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        total_lines = len(all_lines)

        # Apply line range selection
        if start_line is not None or end_line is not None:
            s = max(1, start_line) if start_line is not None else 1
            e = min(total_lines, end_line) if end_line is not None else total_lines
            if s > total_lines:
                return self.success(
                    tool_call_id=tool_call_id,
                    content={
                        "ok": True,
                        "path": str(path),
                        "truncated": False,
                        "total_lines": total_lines,
                        "start_line": s,
                        "end_line": e,
                        "returned_chars": 0,
                        "content": "",
                    },
                )
            selected_lines = all_lines[s - 1 : e]
            # Format with line numbers when a range is specified
            numbered_lines: list[str] = []
            for offset, line in enumerate(selected_lines):
                line_num = s + offset
                numbered_lines.append(f"{line_num:>6}→{line}")
            visible_content = "\n".join(numbered_lines)
        else:
            visible_content = "\n".join(all_lines)

        truncated = len(visible_content) > max_chars
        visible_content = visible_content[:max_chars]
        return self.success(
            tool_call_id=tool_call_id,
            content={
                "ok": True,
                "path": str(path),
                "truncated": truncated,
                "total_lines": total_lines,
                "returned_chars": len(visible_content),
                "content": visible_content,
            },
        )
