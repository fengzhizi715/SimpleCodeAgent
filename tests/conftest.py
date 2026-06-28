"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_default_sqlite_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep tests that use the default SQLite path away from the developer DB."""
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "simple-code-agent-test.sqlite3"))
