"""旧版 data/app.db 迁移到统一主库路径。"""

from __future__ import annotations

import sqlite3

import app.core.config as app_config
import pytest

from app.db import sqlite as sqlite_mod


def test_migrates_data_app_db_to_unified_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("SQLITE_DB_PATH", raising=False)
    monkeypatch.setattr(app_config, "BASE_DIR", tmp_path)
    legacy = tmp_path / "data" / "app.db"
    legacy.parent.mkdir(parents=True)
    conn = sqlite3.connect(legacy)
    conn.execute("CREATE TABLE IF NOT EXISTS t(x INT)")
    conn.commit()
    conn.close()

    db = sqlite_mod.SQLiteDB()
    assert db.db_path == tmp_path / ".simple_code_agent.sqlite3"
    assert not legacy.exists()
    assert db.db_path.exists()

    with db.connect() as c:
        rows = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    assert any("t" in str(r) for r in rows)


def test_explicit_db_path_skips_legacy(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """传入显式路径时不触发 data/app.db 迁移。"""
    monkeypatch.delenv("SQLITE_DB_PATH", raising=False)
    monkeypatch.setattr(app_config, "BASE_DIR", tmp_path)
    legacy = tmp_path / "data" / "app.db"
    legacy.parent.mkdir(parents=True)
    conn = sqlite3.connect(legacy)
    conn.execute("CREATE TABLE t(x INT)")
    conn.commit()
    conn.close()

    custom = tmp_path / "custom.sqlite3"
    db = sqlite_mod.SQLiteDB(custom)
    assert db.db_path == custom
    assert legacy.exists()
