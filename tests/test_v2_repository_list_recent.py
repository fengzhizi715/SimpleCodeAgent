"""V2Repository 最近运行列表。"""

from __future__ import annotations

from app.contracts.agent import AgentArtifact, SharedWorkspace
from app.contracts.message import ChatMessage
from app.contracts.run import RunChoice, RunResult
from app.db.sqlite import SQLiteDB
from app.v1.memory.repository import SQLiteMemoryRepository
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
    assert rows[0]["agent_version"] == "v2"
    assert rows[1]["run_id"] == "run-a"
    assert rows[1]["agent_version"] == "v2"

    page = repo.list_recent_runs_with_workspace(limit=1, offset=1)
    assert len(page) == 1
    assert page[0]["run_id"] == "run-a"


def test_ensure_run_does_not_overwrite_task_with_artifact_placeholder(tmp_path) -> None:
    """save_artifacts 会调用 ensure_run(artifact-only)；不得覆盖用户真实 task/model。"""
    db = SQLiteDB(tmp_path / "e.sqlite3")
    repo = V2Repository(db)
    repo.ensure_run(run_id="r1", session_id="s1", model="my-model", task="分析目录结构", status="running")
    repo.ensure_run(run_id="r1", session_id="s1", model="<artifact-only>", task="<artifact-only>", status="running")
    row = db.fetchone("SELECT model, task FROM runs WHERE run_id = ?", ("r1",))
    assert row["model"] == "my-model"
    assert row["task"] == "分析目录结构"

    repo.save_artifacts(
        run_id="r1",
        session_id="s1",
        artifacts=[AgentArtifact(key="k", type="t", summary="s")],
    )
    row2 = db.fetchone("SELECT model, task FROM runs WHERE run_id = ?", ("r1",))
    assert row2["model"] == "my-model"
    assert row2["task"] == "分析目录结构"


def test_list_recent_runs_hides_v1_internal_plan_runs(tmp_path) -> None:
    db = SQLiteDB(tmp_path / "hist-v1.sqlite3")
    memory_repo = SQLiteMemoryRepository(db_path=db.db_path)
    repo = V2Repository(db)

    common = {
        "model": "fake-model",
        "session_id": "sess-v1",
        "status": "completed",
        "step_count": 1,
        "choices": [RunChoice(index=0, message=ChatMessage(role="assistant", content="ok"))],
    }
    memory_repo.save_run(
        RunResult(
            id="top-run",
            run_id="top-run",
            final_output="顶层结果",
            **common,
        ),
        "帮我分析项目结构",
    )
    memory_repo.save_run(
        RunResult(
            id="direct-run",
            run_id="direct-run",
            final_output="工具结果",
            **common,
        ),
        "[direct-tool] 查看根目录结构",
        is_top_level=False,
        parent_run_id="top-run",
    )
    memory_repo.save_run(
        RunResult(
            id="step-run",
            run_id="step-run",
            final_output="步骤结果",
            **common,
        ),
        "总任务：帮我分析项目结构\n当前是第 2/3 步。\n步骤标题：读取关键文件",
        is_top_level=False,
        parent_run_id="top-run",
    )

    rows = repo.list_recent_runs_with_workspace(limit=10, offset=0)

    assert [row["run_id"] for row in rows] == ["top-run"]
    assert repo.count_runs_with_workspace() == 1
    assert rows[0]["agent_version"] == "v1"
