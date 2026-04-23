"""V2Repository 最近运行列表。"""

from __future__ import annotations

from app.contracts.agent import SharedWorkspace
from app.db.sqlite import SQLiteDB
from app.v2.repository import V2Repository


def test_list_recent_runs_with_workspace_orders_by_updated_at(tmp_path) -> None:
    db = SQLiteDB(tmp_path / "hist.sqlite3")
    repo = V2Repository(db)

    repo.ensure_run(
        run_id="run-a",
        session_id="sess-1",
        model="m1",
        task="task a",
        status="completed",
    )
    repo.save_workspace(
        SharedWorkspace(session_id="sess-1", run_id="run-a", user_goal="goal a")
    )

    repo.ensure_run(
        run_id="run-b",
        session_id="sess-1",
        model="m1",
        task="task b",
        status="failed",
    )
    repo.save_workspace(
        SharedWorkspace(session_id="sess-1", run_id="run-b", user_goal="goal b")
    )

    rows = repo.list_recent_runs_with_workspace(limit=10, offset=0)
    assert len(rows) == 2
    # run-b 后写入，updated_at 更晚，应排在首位
    assert rows[0]["run_id"] == "run-b"
    assert rows[0]["user_goal"] == "goal b"
    assert rows[1]["run_id"] == "run-a"

    page = repo.list_recent_runs_with_workspace(limit=1, offset=1)
    assert len(page) == 1
    assert page[0]["run_id"] == "run-a"
