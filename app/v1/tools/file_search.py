"""文件搜索工具。"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from app.contracts.tool import ToolDefinition, ToolResult
from app.core.exceptions import AppError
from app.v1.tools.base import Tool

# 常见的不应搜索的目录名，仿 .gitignore 行为
_IGNORED_DIR_NAMES: frozenset[str] = frozenset({
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".tox",
    ".eggs",
    "dist",
    "build",
    "eggs",
    ".idea",
    ".vscode",
    ".chroma",
    ".traces",
    "htmlcov",
    ".hypothesis",
    ".qoder",
})

# 不应搜索的文件扩展名或文件名模式
_IGNORED_FILE_PATTERNS: frozenset[str] = frozenset({
    "*.pyc",
    "*.pyo",
    "*.so",
    "*.egg",
    "*.whl",
    "*.sqlite3",
    "*.db",
    "*.log",
    "*.tmp",
    "*.bak",
    ".DS_Store",
    "Thumbs.db",
})


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
            if self._should_ignore(path):
                continue
            try:
                safe_path = self.resolve_path(str(path))
            except AppError:
                continue
            if glob_pattern and not self._matches_glob(path, glob_pattern):
                continue

            try:
                lines = safe_path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue

            for line_number, line in enumerate(lines, start=1):
                if query in line:
                    matches.append(
                        {
                            "path": str(safe_path),
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

    def _should_ignore(self, path: Path) -> bool:
        """判断文件是否应被忽略（基于目录名和文件名模式）。"""
        # 检查路径中是否包含应忽略的目录
        for part in path.parts:
            if part in _IGNORED_DIR_NAMES:
                return True
        # 检查文件名是否匹配应忽略的文件模式
        name = path.name
        for pattern in _IGNORED_FILE_PATTERNS:
            if fnmatch.fnmatch(name, pattern):
                return True
        return False
