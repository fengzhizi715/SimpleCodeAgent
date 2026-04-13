"""工具基类。"""

from __future__ import annotations

import difflib
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.contracts.tool import ToolDefinition, ToolResult
from app.core.config import BASE_DIR
from app.core.exceptions import AppError


class Tool(ABC):
    """所有工具的抽象基类。"""

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self._workspace_root = Path(workspace_root).expanduser().resolve() if workspace_root else BASE_DIR.resolve()

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """返回暴露给模型的工具定义。"""

    @abstractmethod
    def execute(self, arguments: dict[str, Any], tool_call_id: str) -> ToolResult:
        """使用解析后的参数执行工具。"""

    @property
    def workspace_root(self) -> Path:
        """返回工具允许操作的工作区根目录。"""
        return self._workspace_root

    def resolve_path(self, raw_path: str) -> Path:
        """解析路径并确保其位于工作区内。"""
        path = Path(raw_path)
        candidate = (self.workspace_root / path) if not path.is_absolute() else path
        resolved = candidate.resolve(strict=False)
        self._ensure_safe_path(candidate)
        try:
            resolved.relative_to(self.workspace_root.resolve())
        except ValueError as exc:
            raise AppError(f"Path is outside workspace: {raw_path}") from exc
        return resolved

    def _ensure_safe_path(self, candidate: Path) -> None:
        """显式检查路径链路中的符号链接，避免工作区逃逸。"""
        workspace_root = self.workspace_root.resolve()
        current = candidate
        while True:
            if current.exists() and current.is_symlink():
                target = current.resolve(strict=False)
                try:
                    target.relative_to(workspace_root)
                except ValueError as exc:
                    raise AppError(f"Path escapes workspace through symlink: {candidate}") from exc
            if current == workspace_root or current.parent == current:
                break
            current = current.parent

    def success(self, *, tool_call_id: str, content: dict[str, Any]) -> ToolResult:
        """构造一个带 JSON 内容的成功结果。"""
        return ToolResult(
            tool_call_id=tool_call_id,
            name=self.definition.name,
            content=json.dumps(content, ensure_ascii=False, indent=2),
        )

    def error(self, *, tool_call_id: str, message: str, **extra: Any) -> ToolResult:
        """构造一个带 JSON 内容的错误结果。"""
        payload: dict[str, Any] = {"ok": False, "error": message}
        payload.update(extra)
        return ToolResult(
            tool_call_id=tool_call_id,
            name=self.definition.name,
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            is_error=True,
        )

    def build_diff_preview(
        self,
        *,
        path: Path,
        before: str,
        after: str,
        max_lines: int = 200,
    ) -> dict[str, Any]:
        """构造统一 diff 预览，便于编程执行场景查看改动。"""
        try:
            display_path = str(path.relative_to(self.workspace_root))
        except ValueError:
            display_path = str(path)
        diff_lines = list(
            difflib.unified_diff(
                before.splitlines(),
                after.splitlines(),
                fromfile=f"a/{display_path}",
                tofile=f"b/{display_path}",
                lineterm="",
            )
        )
        truncated = len(diff_lines) > max_lines
        preview_lines = diff_lines[:max_lines]
        return {
            "diff_preview": "\n".join(preview_lines),
            "diff_line_count": len(diff_lines),
            "diff_truncated": truncated,
        }


class DummyTool(Tool):
    """用于端到端验证的最小 dummy 工具。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="dummy_tool",
            description="Return a deterministic dummy response for a given input.",
            parameters={
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "Input text sent to the dummy tool.",
                    }
                },
                "required": ["input"],
                "additionalProperties": False,
            },
            strict=True,
        )

    def execute(self, arguments: dict[str, Any], tool_call_id: str) -> ToolResult:
        user_input = str(arguments.get("input", ""))
        return ToolResult(
            tool_call_id=tool_call_id,
            name=self.definition.name,
            content=f"dummy_tool result: {user_input}",
        )
