"""V2 Shared Workspace。"""

from __future__ import annotations

from typing import Any

from app.contracts.agent import AgentArtifact, SharedWorkspace, TestReport, WorkspaceArtifactIndex
from app.contracts.planner import Plan


class WorkspaceStore:
    """Shared Workspace 的轻量封装。"""

    def __init__(self, workspace: SharedWorkspace) -> None:
        self.workspace = workspace

    def set_plan(self, plan: Plan) -> None:
        """更新当前计划。"""
        self.workspace.current_plan = plan

    def write_project_summary(self, summary: str) -> None:
        """更新项目摘要。"""
        self.workspace.project_summary = summary.strip()

    def write_patch_summary(self, summary: str) -> None:
        """更新最近补丁摘要。"""
        self.workspace.latest_patch_summary = summary.strip()

    def write_test_result(self, report: TestReport) -> None:
        """更新最近测试结果。"""
        self.workspace.latest_test_result = report

    def append_note(self, note: str) -> None:
        """记录执行备注。"""
        if note.strip():
            self.workspace.execution_notes.append(note.strip())

    def upsert_private_context(self, agent_id: str, payload: dict[str, Any]) -> None:
        """写入指定 Agent 的私有上下文。"""
        self.workspace.private_context[agent_id] = dict(payload)

    def add_artifact(
        self,
        *,
        key: str,
        artifact_type: str,
        summary: str,
        metadata: dict[str, Any] | None = None,
        latest_artifact_id: str | None = None,
    ) -> None:
        """登记一个共享工件。"""
        for index, artifact in enumerate(self.workspace.artifacts_index):
            if artifact.key == key:
                self.workspace.artifacts_index[index] = WorkspaceArtifactIndex(
                    key=key,
                    type=artifact_type,
                    summary=summary,
                    latest_artifact_id=latest_artifact_id or artifact.latest_artifact_id,
                    version=artifact.version + 1,
                    metadata=metadata or {},
                )
                return
        self.workspace.artifacts_index.append(
            WorkspaceArtifactIndex(
                key=key,
                type=artifact_type,
                summary=summary,
                latest_artifact_id=latest_artifact_id,
                version=1,
                metadata=metadata or {},
            )
        )

    def upsert_agent_artifacts(self, artifacts: list[AgentArtifact]) -> None:
        """将 Agent 输出的工件同步到 workspace 索引。"""
        for artifact in artifacts:
            self.add_artifact(
                key=artifact.key,
                artifact_type=artifact.type,
                summary=artifact.summary,
                metadata={"producer_agent": artifact.producer_agent},
                latest_artifact_id=artifact.artifact_id,
            )
