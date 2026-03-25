"""文件搜索工具。"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from app.contracts.tool import ToolDefinition, ToolResult
from app.tools.base import Tool


class FileSearchTool(Tool):
    """在工作区文件中搜索文本。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="file_search",
            description="Search for a keyword in workspace files and return matching lines.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keyword to search for."},
                    "glob": {
                        "type": "string",
                        "description": "Optional glob filter like app/**/*.py or *.md.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of matches to return.",
                        "default": 20,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            strict=True,
        )

    def execute(self, arguments: dict[str, object], tool_call_id: str) -> ToolResult:
        query = str(arguments.get("query", "")).strip()
        glob_pattern = str(arguments.get("glob", "")).strip() or None
        max_results = int(arguments.get("max_results", 20))
        if not query:
            return self.error(tool_call_id=tool_call_id, message="Query must not be empty.")

        matches: list[dict[str, object]] = []
        for path in self.workspace_root.rglob("*"):
            if not path.is_file():
                continue
            if ".venv" in path.parts or "__pycache__" in path.parts:
                continue
            if glob_pattern and not self._matches_glob(path, glob_pattern):
                continue

            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue

            for line_number, line in enumerate(lines, start=1):
                if query in line:
                    matches.append(
                        {
                            "path": str(path),
                            "line": line_number,
                            "snippet": line.strip(),
                        }
                    )
                    if len(matches) >= max_results:
                        return self.success(
                            tool_call_id=tool_call_id,
                            content={
                                "ok": True,
                                "query": query,
                                "glob": glob_pattern,
                                "truncated": True,
                                "matches": matches,
                            },
                        )

        return self.success(
            tool_call_id=tool_call_id,
            content={
                "ok": True,
                "query": query,
                "glob": glob_pattern,
                "truncated": False,
                "matches": matches,
            },
        )

    def _matches_glob(self, path: Path, pattern: str) -> bool:
        """支持简单的绝对路径和相对路径 glob 匹配。"""
        relative = str(path.relative_to(self.workspace_root))
        return fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(path.name, pattern)
