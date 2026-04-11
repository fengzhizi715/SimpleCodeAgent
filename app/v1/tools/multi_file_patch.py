"""多文件批量修改工具。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.contracts.tool import ToolDefinition, ToolResult
from app.v1.tools.base import Tool


class MultiFilePatchTool(Tool):
    """在一次工具调用中批量修改多个文件。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="multi_file_patch",
            description="Apply multiple file edits in one call. Supports write, append, and replace operations.",
            parameters={
                "type": "object",
                "properties": {
                    "patches": {
                        "type": "array",
                        "description": "List of file patch operations.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "mode": {
                                    "type": "string",
                                    "enum": ["write", "append", "replace"],
                                    "description": "Patch mode.",
                                },
                                "path": {"type": "string", "description": "Target file path."},
                                "content": {
                                    "type": "string",
                                    "description": "Used by write and append modes.",
                                },
                                "old_text": {
                                    "type": "string",
                                    "description": "Used by replace mode.",
                                },
                                "new_text": {
                                    "type": "string",
                                    "description": "Used by replace mode.",
                                },
                            },
                            "required": ["mode", "path"],
                            "additionalProperties": False,
                        },
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, preview the changes without writing files.",
                        "default": False,
                    },
                },
                "required": ["patches"],
                "additionalProperties": False,
            },
            strict=True,
        )

    def execute(self, arguments: dict[str, object], tool_call_id: str) -> ToolResult:
        raw_patches = arguments.get("patches", [])
        dry_run = bool(arguments.get("dry_run", False))
        if not isinstance(raw_patches, list) or not raw_patches:
            return self.error(tool_call_id=tool_call_id, message="Patches must be a non-empty array.")

        try:
            planned_patches = [self._plan_patch(raw_patch) for raw_patch in raw_patches]
        except ValueError as exc:
            return self.error(tool_call_id=tool_call_id, message=str(exc))

        if not dry_run:
            for planned_patch in planned_patches:
                path = planned_patch["path"]
                after = planned_patch["after"]
                assert isinstance(path, Path)
                assert isinstance(after, str)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(after, encoding="utf-8")

        return self.success(
            tool_call_id=tool_call_id,
            content={
                "ok": True,
                "dry_run": dry_run,
                "file_count": len(planned_patches),
                "patches": [
                    {
                        "mode": planned_patch["mode"],
                        "path": str(planned_patch["path"]),
                        "created": planned_patch["created"],
                        "bytes": len(str(planned_patch["after"]).encode("utf-8")),
                        "replacements": planned_patch.get("replacements", 0),
                        **planned_patch["diff_payload"],
                    }
                    for planned_patch in planned_patches
                ],
            },
        )

    def _plan_patch(self, raw_patch: object) -> dict[str, Any]:
        if not isinstance(raw_patch, dict):
            raise ValueError("Each patch must be an object.")

        mode = str(raw_patch.get("mode", "")).strip().lower()
        raw_path = str(raw_patch.get("path", "")).strip()
        if mode not in {"write", "append", "replace"}:
            raise ValueError(f"Unsupported patch mode: {mode or '<empty>'}")
        if not raw_path:
            raise ValueError("Patch path must not be empty.")

        path = self.resolve_path(raw_path)
        existed_before = path.exists()
        before = path.read_text(encoding="utf-8", errors="replace") if existed_before and path.is_file() else ""

        replacements = 0
        if mode == "write":
            after = str(raw_patch.get("content", ""))
        elif mode == "append":
            append_content = str(raw_patch.get("content", ""))
            after = f"{before}{append_content}"
        else:
            old_text = str(raw_patch.get("old_text", ""))
            new_text = str(raw_patch.get("new_text", ""))
            if not existed_before or not path.is_file():
                raise ValueError(f"File not found for replace patch: {raw_path}")
            replacements = before.count(old_text)
            if replacements == 0:
                raise ValueError(f"Target text not found for replace patch: {raw_path}")
            after = before.replace(old_text, new_text)

        return {
            "mode": mode,
            "path": path,
            "created": not existed_before,
            "before": before,
            "after": after,
            "replacements": replacements,
            "diff_payload": self.build_diff_preview(path=path, before=before, after=after),
        }
