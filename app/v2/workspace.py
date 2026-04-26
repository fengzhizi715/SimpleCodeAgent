"""V2 Shared Workspace。"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.contracts.agent import AgentArtifact, SharedWorkspace, TestReport, WorkspaceArtifactIndex
from app.contracts.planner import Plan
from app.v2.agent_impls.workspace_diff import relative_path
from app.v2.memory import PrivateMemory, SharedMemory


class WorkspaceStore:
    """Shared Workspace 的轻量封装。"""

    def __init__(self, workspace: SharedWorkspace, *, workspace_root: Path | None = None) -> None:
        self.workspace = workspace
        self.workspace_root = workspace_root
        self.shared_memory = SharedMemory(workspace)
        self.private_memory = PrivateMemory(workspace)

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
        self.private_memory.write(agent_id, payload)

    def merge_analyst_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        """增量合并 analyst 上下文，避免后续步骤覆盖已有高价值信息。"""
        existing = dict(self.workspace.private_context.get("analyst", {}))
        merged: dict[str, Any] = dict(existing)
        analysis_mode = str(payload.get("analysis_mode") or "").strip()
        merged["analysis_mode"] = analysis_mode or str(existing.get("analysis_mode") or "")

        merged["project_summary"] = self._merge_summary(
            str(existing.get("project_summary") or self.workspace.project_summary or ""),
            str(payload.get("project_summary") or ""),
            analysis_mode=analysis_mode,
        )
        merged["module_responsibilities"] = self._merge_dict_of_strings(
            existing.get("module_responsibilities"),
            payload.get("module_responsibilities"),
        )
        merged["entry_files"] = self._merge_string_lists(
            existing.get("entry_files"),
            payload.get("entry_files"),
        )
        merged["coding_hints"] = self._merge_string_lists(
            existing.get("coding_hints"),
            payload.get("coding_hints"),
        )
        merged["key_files"] = self._merge_key_files(
            existing.get("key_files"),
            payload.get("key_files"),
        )

        for field in ("root_entries", "highlighted_files"):
            merged[field] = self._merge_object_lists(existing.get(field), payload.get(field))

        merged["docs_context"] = self._merge_docs_context(
            existing.get("docs_context"),
            payload.get("docs_context"),
        )

        self.workspace.private_context["analyst"] = merged
        if merged["project_summary"]:
            self.workspace.project_summary = str(merged["project_summary"]).strip()
        return merged

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

    def _merge_summary(self, existing: str, incoming: str, *, analysis_mode: str) -> str:
        incoming_clean = incoming.strip()
        existing_clean = existing.strip()
        if not existing_clean:
            return incoming_clean
        if not incoming_clean:
            return existing_clean
        if analysis_mode == "summary":
            return incoming_clean
        if self._summary_score(incoming_clean) >= self._summary_score(existing_clean):
            return incoming_clean
        if incoming_clean in existing_clean:
            return existing_clean
        return existing_clean

    def _summary_score(self, summary: str) -> tuple[int, int]:
        text = summary.strip()
        penalty = 0
        if "顶层结构包含" in text:
            penalty -= 2
        if "任务分析目标" in text:
            penalty -= 1
        if text.count("。") > 4:
            penalty -= 1
        reward = 0
        if any(token in text for token in ("Compose", "Gradle", "OpenCV", "ONNX", "Kotlin", "模块")):
            reward += 2
        if len(text) <= 220:
            reward += 1
        return reward + penalty, len(text)

    def _merge_dict_of_strings(self, existing: object, incoming: object) -> dict[str, str]:
        merged: dict[str, str] = {}
        for candidate in (existing, incoming):
            if not isinstance(candidate, dict):
                continue
            for key, value in candidate.items():
                key_str = str(key).strip()
                value_str = str(value).strip()
                if key_str and value_str:
                    merged[key_str] = value_str
        return merged

    def _merge_string_lists(self, existing: object, incoming: object) -> list[str]:
        merged: list[str] = []
        for source in (existing, incoming):
            if not isinstance(source, Iterable) or isinstance(source, (str, bytes, dict)):
                continue
            for item in source:
                value = self._normalize_path_like_value(str(item).strip())
                if value and value not in merged:
                    merged.append(value)
        return merged

    def _merge_key_files(self, existing: object, incoming: object) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        by_path: dict[str, dict[str, Any]] = {}
        for source in (existing, incoming):
            if not isinstance(source, list):
                continue
            for item in source:
                if not isinstance(item, dict):
                    continue
                path = self._normalize_path_like_value(str(item.get("path") or "").strip())
                reason = str(item.get("reason") or "").strip()
                if not path:
                    continue
                current = by_path.get(path, {"path": path, "reason": ""})
                if reason:
                    current["reason"] = reason if len(reason) >= len(current["reason"]) else current["reason"]
                by_path[path] = current
        for value in by_path.values():
            merged.append(value)
        return merged

    def _merge_object_lists(self, existing: object, incoming: object) -> list[Any]:
        if isinstance(incoming, list) and incoming:
            return list(incoming)
        if isinstance(existing, list):
            return list(existing)
        return []

    def _merge_docs_context(self, existing: object, incoming: object) -> dict[str, Any]:
        existing_data = dict(existing) if isinstance(existing, dict) else {}
        incoming_data = dict(incoming) if isinstance(incoming, dict) else {}
        if not incoming_data:
            return existing_data
        if not existing_data:
            return incoming_data

        merged = dict(existing_data)
        for field in ("query", "rag_id", "rag_ids", "match_count"):
            if incoming_data.get(field) not in (None, "", []):
                merged[field] = incoming_data[field]
        merged["matches"] = self._merge_doc_matches(
            existing_data.get("matches"),
            incoming_data.get("matches"),
        )
        return merged

    def _merge_doc_matches(self, existing: object, incoming: object) -> list[Any]:
        merged: list[Any] = []
        seen: set[str] = set()
        for source in (existing, incoming):
            if not isinstance(source, list):
                continue
            for item in source:
                key = self._doc_match_key(item)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
        return merged

    def _doc_match_key(self, item: object) -> str:
        if isinstance(item, dict):
            for field in ("id", "document_id", "source", "path", "title", "content"):
                value = str(item.get(field) or "").strip()
                if value:
                    return f"{field}:{value[:160]}"
        return repr(item)[:160]

    def _normalize_path_like_value(self, value: str) -> str:
        if not value.startswith("/"):
            return value
        if self.workspace_root is not None:
            try:
                return relative_path(self.workspace_root, Path(value))
            except Exception:
                return value
        try:
            return relative_path(Path.cwd(), Path(value))
        except Exception:
            return value
