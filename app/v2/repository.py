"""V2 持久化仓储。"""

from __future__ import annotations

import json
from typing import Any

from app.contracts.agent import AgentArtifact, DelegationRecord, SharedWorkspace
from app.contracts.run import RunResult
from app.db.sqlite import SQLiteDB


class V2Repository:
    """负责 V2 runs / workspace / delegation 的持久化与查询。"""

    def __init__(self, db: SQLiteDB) -> None:
        self.db = db

    def ensure_session(self, session_id: str) -> None:
        """确保 session 记录存在。"""
        timestamp = self.db.now()
        self.db.execute(
            """
            INSERT INTO sessions (id, created_at, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (session_id, timestamp, timestamp),
        )

    def ensure_run(
        self,
        *,
        run_id: str,
        session_id: str,
        model: str,
        task: str,
        workdir: str | None = None,
        is_top_level: bool = True,
        parent_run_id: str | None = None,
        status: str = "running",
    ) -> None:
        """确保 run 记录存在，供 trace/workspace/delegation 提前关联。"""
        self.ensure_session(session_id)
        timestamp = self.db.now()
        self.db.execute(
            """
            INSERT INTO runs (
                run_id, session_id, model, task, workdir, is_top_level, parent_run_id, status, step_count, final_output,
                created_at, updated_at, agent_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, '', ?, ?, 'v2')
            ON CONFLICT(run_id) DO UPDATE SET
                session_id = excluded.session_id,
                model = CASE
                    WHEN excluded.model = '<artifact-only>' THEN runs.model
                    ELSE excluded.model
                END,
                task = CASE
                    WHEN excluded.task = '<artifact-only>' THEN runs.task
                    ELSE excluded.task
                END,
                workdir = CASE
                    WHEN excluded.task = '<artifact-only>' THEN runs.workdir
                    ELSE COALESCE(excluded.workdir, runs.workdir)
                END,
                is_top_level = CASE
                    WHEN excluded.task = '<artifact-only>' THEN runs.is_top_level
                    ELSE excluded.is_top_level
                END,
                parent_run_id = CASE
                    WHEN excluded.task = '<artifact-only>' THEN runs.parent_run_id
                    ELSE excluded.parent_run_id
                END,
                status = excluded.status,
                agent_version = 'v2',
                updated_at = excluded.updated_at
            """,
            (
                run_id,
                session_id,
                model,
                task,
                workdir,
                1 if is_top_level else 0,
                parent_run_id,
                status,
                timestamp,
                timestamp,
            ),
        )

    def save_run(
        self,
        result: RunResult,
        task: str,
        *,
        workdir: str | None = None,
        is_top_level: bool = True,
        parent_run_id: str | None = None,
    ) -> None:
        """持久化 V2 run 元数据。"""
        if not result.run_id or not result.session_id:
            return
        self.ensure_session(result.session_id)
        timestamp = self.db.now()
        usage = result.usage
        self.db.execute(
            """
            INSERT INTO runs (
                run_id, session_id, model, task, workdir, is_top_level, parent_run_id, status, step_count, final_output,
                prompt_tokens, completion_tokens, total_tokens, created_at, updated_at, agent_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'v2')
            ON CONFLICT(run_id) DO UPDATE SET
                model = CASE
                    WHEN excluded.model = '' THEN runs.model
                    ELSE excluded.model
                END,
                task = excluded.task,
                workdir = COALESCE(excluded.workdir, runs.workdir),
                is_top_level = excluded.is_top_level,
                parent_run_id = excluded.parent_run_id,
                status = excluded.status,
                step_count = excluded.step_count,
                final_output = excluded.final_output,
                prompt_tokens = excluded.prompt_tokens,
                completion_tokens = excluded.completion_tokens,
                total_tokens = excluded.total_tokens,
                agent_version = 'v2',
                updated_at = excluded.updated_at
            """,
            (
                result.run_id,
                result.session_id,
                result.model,
                task,
                workdir,
                1 if is_top_level else 0,
                parent_run_id,
                result.status,
                result.step_count,
                result.final_output,
                usage.prompt_tokens if usage is not None else 0,
                usage.completion_tokens if usage is not None else 0,
                usage.total_tokens if usage is not None else 0,
                timestamp,
                timestamp,
            ),
        )

    def save_workspace(self, workspace: SharedWorkspace) -> None:
        """持久化当前 workspace 快照。"""
        self.ensure_session(workspace.session_id)
        timestamp = self.db.now()
        self.db.execute(
            """
            INSERT INTO v2_workspaces (
                run_id,
                session_id,
                user_goal,
                current_plan_json,
                project_summary,
                latest_patch_summary,
                latest_test_result_json,
                artifacts_index_json,
                execution_notes_json,
                private_context_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                current_plan_json = excluded.current_plan_json,
                project_summary = excluded.project_summary,
                latest_patch_summary = excluded.latest_patch_summary,
                latest_test_result_json = excluded.latest_test_result_json,
                artifacts_index_json = excluded.artifacts_index_json,
                execution_notes_json = excluded.execution_notes_json,
                private_context_json = excluded.private_context_json,
                updated_at = excluded.updated_at
            """,
            (
                workspace.run_id,
                workspace.session_id,
                workspace.user_goal,
                json.dumps(
                    workspace.current_plan.model_dump() if workspace.current_plan else {},
                    ensure_ascii=False,
                ),
                workspace.project_summary,
                workspace.latest_patch_summary,
                json.dumps(
                    workspace.latest_test_result.model_dump()
                    if workspace.latest_test_result is not None
                    else {},
                    ensure_ascii=False,
                ),
                json.dumps(
                    [item.model_dump() for item in workspace.artifacts_index],
                    ensure_ascii=False,
                ),
                json.dumps(workspace.execution_notes, ensure_ascii=False),
                json.dumps(workspace.private_context, ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )

    def save_delegation(self, delegation: DelegationRecord) -> None:
        """持久化或更新单条 delegation 记录。"""
        self.ensure_session(delegation.session_id)
        self.db.execute(
            """
            INSERT INTO v2_delegations (
                delegation_id,
                run_id,
                session_id,
                step_id,
                parent_agent_id,
                target_agent,
                task_id,
                status,
                summary,
                error_message,
                started_at,
                finished_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(delegation_id) DO UPDATE SET
                status = excluded.status,
                summary = excluded.summary,
                error_message = excluded.error_message,
                finished_at = excluded.finished_at
            """,
            (
                delegation.delegation_id,
                delegation.run_id,
                delegation.session_id,
                delegation.step_id,
                delegation.parent_agent_id,
                delegation.target_agent,
                delegation.task_id,
                delegation.status,
                delegation.summary,
                delegation.error_message,
                delegation.started_at,
                delegation.finished_at,
            ),
        )

    def save_artifacts(
        self,
        *,
        run_id: str,
        session_id: str,
        artifacts: list[AgentArtifact],
    ) -> None:
        """持久化本次 run 产生的工件内容。"""
        if not artifacts:
            return
        self.ensure_run(
            run_id=run_id,
            session_id=session_id,
            model="<artifact-only>",
            task="<artifact-only>",
            status="running",
        )
        timestamp = self.db.now()
        rows = [
            (
                artifact.artifact_id,
                run_id,
                session_id,
                artifact.key,
                artifact.type,
                artifact.version,
                artifact.producer_agent,
                artifact.summary,
                json.dumps(artifact.content, ensure_ascii=False),
                timestamp,
            )
            for artifact in artifacts
        ]
        self.db.executemany(
            """
            INSERT OR REPLACE INTO v2_artifacts (
                artifact_id,
                run_id,
                session_id,
                key,
                type,
                version,
                producer_agent,
                summary,
                content_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    def get_workspace(self, run_id: str) -> SharedWorkspace | None:
        """读取指定 run 的 workspace 快照。"""
        row = self.db.fetchone(
            """
            SELECT *
            FROM v2_workspaces
            WHERE run_id = ?
            """,
            (run_id,),
        )
        if row is None:
            return None
        current_plan = json.loads(row["current_plan_json"]) if row["current_plan_json"] else {}
        latest_test_result = (
            json.loads(row["latest_test_result_json"])
            if row["latest_test_result_json"]
            else {}
        )
        return SharedWorkspace.model_validate(
            {
                "run_id": row["run_id"],
                "session_id": row["session_id"],
                "user_goal": row["user_goal"],
                "current_plan": current_plan or None,
                "project_summary": row["project_summary"],
                "latest_patch_summary": row["latest_patch_summary"],
                "latest_test_result": latest_test_result or None,
                "artifacts_index": json.loads(row["artifacts_index_json"] or "[]"),
                "execution_notes": json.loads(row["execution_notes_json"] or "[]"),
                "private_context": json.loads(row["private_context_json"] or "{}"),
            }
        )

    def list_delegations_for_run(self, run_id: str) -> list[DelegationRecord]:
        """列出某次 run 的全部委派记录。"""
        rows = self.db.fetchall(
            """
            SELECT *
            FROM v2_delegations
            WHERE run_id = ?
            ORDER BY started_at ASC, delegation_id ASC
            """,
            (run_id,),
        )
        return [DelegationRecord.model_validate(dict(row)) for row in rows]

    def list_artifacts_for_run(self, run_id: str) -> list[AgentArtifact]:
        """列出某次 run 的 artifact 历史。"""
        rows = self.db.fetchall(
            """
            SELECT artifact_id, key, type, version, producer_agent, summary, content_json
            FROM v2_artifacts
            WHERE run_id = ?
            ORDER BY created_at ASC, artifact_id ASC
            """,
            (run_id,),
        )
        return [
            AgentArtifact.model_validate(
                {
                    "artifact_id": row["artifact_id"],
                    "key": row["key"],
                    "type": row["type"],
                    "version": row["version"],
                    "producer_agent": row["producer_agent"],
                    "summary": row["summary"],
                    "content": json.loads(row["content_json"] or "{}"),
                }
            )
            for row in rows
        ]

    def list_recent_runs_with_workspace(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """列出最近运行历史（含 v1/v2；过滤 trace/artifact 占位记录）。"""
        rows = self.db.fetchall(
            """
            SELECT
                r.run_id,
                r.session_id,
                r.model,
                r.task,
                r.status,
                r.step_count,
                r.final_output,
                r.created_at,
                r.updated_at,
                COALESCE(w.user_goal, r.task) AS user_goal,
                COALESCE(r.agent_version, CASE WHEN w.run_id IS NOT NULL THEN 'v2' ELSE 'v1' END) AS agent_version
            FROM runs r
            LEFT JOIN v2_workspaces w ON w.run_id = r.run_id
            WHERE r.task NOT IN ('<trace-only>', '<artifact-only>')
              AND r.task NOT LIKE '[direct-tool]%'
              AND r.task NOT LIKE '总任务：%'
              AND r.task NOT LIKE '请基于以下步骤结果%'
              AND (
                COALESCE(r.is_top_level, 1) = 1
                OR (
                  COALESCE(r.agent_version, CASE WHEN w.run_id IS NOT NULL THEN 'v2' ELSE 'v1' END) = 'v1'
                )
              )
              AND r.session_id NOT LIKE '%:v2:coder'
            ORDER BY r.updated_at DESC, r.run_id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        return [
            self._with_effective_status(dict(row), self.get_workspace(row["run_id"]))
            for row in rows
        ]

    def count_runs_with_workspace(self) -> int:
        """统计运行历史总数（含 v1/v2；过滤 trace/artifact 占位记录）。"""
        row = self.db.fetchone(
            """
            SELECT COUNT(1) AS cnt
            FROM runs
            WHERE task NOT IN ('<trace-only>', '<artifact-only>')
              AND task NOT LIKE '[direct-tool]%'
              AND task NOT LIKE '总任务：%'
              AND task NOT LIKE '请基于以下步骤结果%'
              AND (
                COALESCE(is_top_level, 1) = 1
                OR (
                  COALESCE(agent_version, 'v1') = 'v1'
                )
              )
              AND session_id NOT LIKE '%:v2:coder'
            """
        )
        return int(row["cnt"]) if row is not None else 0

    def get_usage_summary_for_ui(self, *, recent_limit: int = 20) -> dict[str, Any]:
        """聚合顶层运行的 token usage，供 Dashboard 展示。"""
        where_clause = """
            task NOT IN ('<trace-only>', '<artifact-only>')
            AND task NOT LIKE '[direct-tool]%'
            AND task NOT LIKE '总任务：%'
            AND task NOT LIKE '请基于以下步骤结果%'
            AND (
              COALESCE(is_top_level, 1) = 1
              OR COALESCE(agent_version, 'v1') = 'v1'
            )
            AND session_id NOT LIKE '%:v2:coder'
        """
        totals = self.db.fetchone(
            f"""
            SELECT
                COUNT(1) AS run_count,
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens
            FROM runs
            WHERE {where_clause}
            """
        )
        by_version = self.db.fetchall(
            f"""
            SELECT
                COALESCE(agent_version, 'v1') AS agent_version,
                COUNT(1) AS run_count,
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens
            FROM runs
            WHERE {where_clause}
            GROUP BY COALESCE(agent_version, 'v1')
            ORDER BY total_tokens DESC, run_count DESC
            """
        )
        by_model = self.db.fetchall(
            f"""
            SELECT
                model,
                COUNT(1) AS run_count,
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens
            FROM runs
            WHERE {where_clause}
            GROUP BY model
            ORDER BY total_tokens DESC, run_count DESC
            """
        )
        by_day = self.db.fetchall(
            f"""
            SELECT
                substr(updated_at, 1, 10) AS day,
                COUNT(1) AS run_count,
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens
            FROM runs
            WHERE {where_clause}
            GROUP BY substr(updated_at, 1, 10)
            ORDER BY day DESC
            LIMIT 14
            """
        )
        recent_runs = self.db.fetchall(
            f"""
            SELECT
                run_id,
                session_id,
                model,
                task,
                status,
                COALESCE(agent_version, 'v1') AS agent_version,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                updated_at
            FROM runs
            WHERE {where_clause}
            ORDER BY total_tokens DESC, updated_at DESC
            LIMIT ?
            """,
            (recent_limit,),
        )
        return {
            "totals": dict(totals) if totals is not None else {},
            "by_version": [dict(row) for row in by_version],
            "by_model": [dict(row) for row in by_model],
            "by_day": [dict(row) for row in by_day],
            "recent_runs": [dict(row) for row in recent_runs],
        }

    def delete_run_for_ui(self, run_id: str) -> bool:
        """删除单条 run 及其 V2 关联数据。"""
        run = self.db.fetchone("SELECT run_id FROM runs WHERE run_id = ?", (run_id,))
        if run is None:
            return False
        # 由于 schema 未配置 ON DELETE CASCADE，需要按依赖顺序手动删除子表记录。
        self.db.execute("DELETE FROM v2_artifacts WHERE run_id = ?", (run_id,))
        self.db.execute("DELETE FROM v2_delegations WHERE run_id = ?", (run_id,))
        self.db.execute("DELETE FROM v2_workspaces WHERE run_id = ?", (run_id,))
        self.db.execute("DELETE FROM trace_index WHERE run_id = ?", (run_id,))
        self.db.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
        return True

    def list_run_replay(self, run_id: str) -> dict[str, Any]:
        """构造某个 run 的回放数据。"""
        run_row = self.db.fetchone(
            """
            SELECT run_id, session_id, model, task, workdir, status, step_count, final_output, created_at, updated_at
            FROM runs
            WHERE run_id = ?
            """,
            (run_id,),
        )
        if run_row is None:
            return {}
        workspace = self.get_workspace(run_id)
        return {
            "run": self._with_effective_status(dict(run_row), workspace),
            "workspace": workspace.model_dump() if workspace is not None else None,
            "delegations": [record.model_dump() for record in self.list_delegations_for_run(run_id)],
            "artifacts": [artifact.model_dump() for artifact in self.list_artifacts_for_run(run_id)],
        }

    def _with_effective_status(
        self,
        row: dict[str, Any],
        workspace: SharedWorkspace | None,
    ) -> dict[str, Any]:
        """为 UI/replay 派生展示状态，兼容旧 run 中误标 completed 的记录。"""
        if row.get("status") != "completed" or workspace is None:
            return row
        if workspace.latest_test_result is not None and workspace.latest_test_result.status != "passed":
            row["status"] = "failed"
        return row

    def list_session_replay(self, session_id: str) -> dict[str, Any]:
        """按 session 聚合 run / workspace / delegation 回放。"""
        run_rows = self.db.fetchall(
            """
            SELECT run_id, session_id, model, task, status, step_count, final_output, created_at, updated_at
            FROM runs
            WHERE session_id = ?
            ORDER BY created_at ASC, run_id ASC
            """,
            (session_id,),
        )
        runs = [dict(row) for row in run_rows]
        workspaces = []
        delegations = []
        artifacts = []
        for run in runs:
            workspace = self.get_workspace(run["run_id"])
            if workspace is not None:
                workspaces.append(workspace.model_dump())
            delegations.extend(
                record.model_dump()
                for record in self.list_delegations_for_run(run["run_id"])
            )
            artifacts.extend(
                artifact.model_dump()
                for artifact in self.list_artifacts_for_run(run["run_id"])
            )
        return {
            "session_id": session_id,
            "runs": runs,
            "workspaces": workspaces,
            "delegations": delegations,
            "artifacts": artifacts,
        }
