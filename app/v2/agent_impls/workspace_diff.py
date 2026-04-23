"""Workspace snapshot and diff helpers for V2 coder/reviewer."""

from __future__ import annotations

import difflib
from pathlib import Path

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
}


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
    created_files = sorted(path for path in after if path not in before)
    deleted_files = sorted(path for path in before if path not in after)
    modified_files = sorted(
        path for path in before if path in after and before[path] != after[path]
    )
    diff_previews: dict[str, str] = {}
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
        diff_previews[path] = "\n".join(diff_lines[:120])
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
        diff_previews[path] = "\n".join(diff_lines[:120])
    return modified_files, created_files, deleted_files, diff_previews
