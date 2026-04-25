"""Workspace snapshot and diff helpers for V2 coder/reviewer."""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path
from typing import TypedDict

IGNORED_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    ".traces",
    ".chroma",
    "node_modules",
    "dist",
    "build",
}

TEXT_FILE_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".sh",
    ".sql",
    ".java",
    ".kt",
    ".kts",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".vue",
    ".css",
    ".html",
}


class PatchStats(TypedDict):
    files_changed: int
    insertions: int
    deletions: int


class WorkspacePatch(TypedDict):
    modified_files: list[str]
    created_files: list[str]
    deleted_files: list[str]
    diff_previews: dict[str, str]
    patch_diffs: dict[str, str]
    patch_stats: PatchStats
    patch_id: str
    base_snapshot_id: str
    head_snapshot_id: str


def relative_path(workspace_root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(workspace_root))
    except ValueError:
        return str(path)


def is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in TEXT_FILE_SUFFIXES or path.name in {
        "README",
        "README.md",
        "Makefile",
        "Dockerfile",
    }


def snapshot_workspace(workspace_root: Path) -> dict[str, str]:
    """Take a lightweight text snapshot for before/after diff."""
    snapshot: dict[str, str] = {}
    if not workspace_root.exists():
        return snapshot
    for path in workspace_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIR_NAMES for part in path.parts):
            continue
        if not is_text_candidate(path):
            continue
        try:
            snapshot[relative_path(workspace_root, path)] = path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            continue
    return snapshot


def build_workspace_diff(
    *,
    workspace_root: Path,
    before: dict[str, str],
    after: dict[str, str],
) -> tuple[list[str], list[str], list[str], dict[str, str]]:
    patch = build_workspace_patch(workspace_root=workspace_root, before=before, after=after)
    return (
        patch["modified_files"],
        patch["created_files"],
        patch["deleted_files"],
        patch["diff_previews"],
    )


def build_workspace_patch(
    *,
    workspace_root: Path,
    before: dict[str, str],
    after: dict[str, str],
) -> WorkspacePatch:
    created_files = sorted(path for path in after if path not in before)
    deleted_files = sorted(path for path in before if path not in after)
    modified_files = sorted(
        path for path in before if path in after and before[path] != after[path]
    )
    diff_previews: dict[str, str] = {}
    patch_diffs: dict[str, str] = {}
    insertions = 0
    deletions = 0
    for path in created_files + modified_files:
        before_content = before.get(path, "")
        after_content = after.get(path, "")
        diff_lines = list(
            difflib.unified_diff(
                before_content.splitlines(),
                after_content.splitlines(),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                lineterm="",
            )
        )
        patch_text = "\n".join(diff_lines)
        patch_diffs[path] = patch_text
        diff_previews[path] = "\n".join(diff_lines[:120])
        added, removed = _count_changed_lines(diff_lines)
        insertions += added
        deletions += removed
    for path in deleted_files:
        before_content = before.get(path, "")
        diff_lines = list(
            difflib.unified_diff(
                before_content.splitlines(),
                [],
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                lineterm="",
            )
        )
        patch_text = "\n".join(diff_lines)
        patch_diffs[path] = patch_text
        diff_previews[path] = "\n".join(diff_lines[:120])
        added, removed = _count_changed_lines(diff_lines)
        insertions += added
        deletions += removed
    return {
        "modified_files": modified_files,
        "created_files": created_files,
        "deleted_files": deleted_files,
        "diff_previews": diff_previews,
        "patch_diffs": patch_diffs,
        "patch_stats": {
            "files_changed": len(created_files) + len(modified_files) + len(deleted_files),
            "insertions": insertions,
            "deletions": deletions,
        },
        "patch_id": _snapshot_digest(patch_diffs),
        "base_snapshot_id": _snapshot_digest(before),
        "head_snapshot_id": _snapshot_digest(after),
    }


def _count_changed_lines(diff_lines: list[str]) -> tuple[int, int]:
    insertions = 0
    deletions = 0
    for line in diff_lines:
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            insertions += 1
        elif line.startswith("-"):
            deletions += 1
    return insertions, deletions


def _snapshot_digest(items: dict[str, str]) -> str:
    hasher = hashlib.sha256()
    for path in sorted(items):
        hasher.update(path.encode("utf-8", errors="replace"))
        hasher.update(b"\0")
        hasher.update(items[path].encode("utf-8", errors="replace"))
        hasher.update(b"\0")
    return hasher.hexdigest()[:16]
