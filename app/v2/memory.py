"""V2 shared/private memory abstractions and context governance."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.agent import SharedWorkspace


class V2MemoryPolicy(BaseModel):
    """Policy for selecting and trimming V2 memory before prompting agents."""

    model_config = ConfigDict(extra="forbid")

    max_execution_notes: int = Field(default=5, ge=0)
    max_artifacts: int = Field(default=20, ge=0)
    max_list_items: int = Field(default=20, ge=1)
    max_string_chars: int = Field(default=4000, ge=1)
    max_dict_keys: int = Field(default=40, ge=1)
    private_memory_by_agent: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "planner": ["orchestrator"],
            "analyst": ["analyst"],
            "coder": ["analyst"],
            "external_coder": ["analyst", "orchestrator"],
            "tester": ["coder", "analyst"],
            "reviewer": ["coder", "analyst", "reviewer"],
        }
    )


class SharedMemory:
    """Typed facade over the shared workspace fields."""

    def __init__(self, workspace: SharedWorkspace) -> None:
        self.workspace = workspace

    def read(self, key: str) -> Any:
        if key == "current_plan":
            return self.workspace.current_plan.model_dump() if self.workspace.current_plan else None
        if key == "latest_test_result":
            return self.workspace.latest_test_result.model_dump() if self.workspace.latest_test_result else None
        if key == "artifacts_index":
            return [item.model_dump() for item in self.workspace.artifacts_index]
        return getattr(self.workspace, key)

    def snapshot(self, keys: list[str]) -> dict[str, Any]:
        return {key: self.read(key) for key in keys}


class PrivateMemory:
    """Agent-scoped private memory facade."""

    def __init__(self, workspace: SharedWorkspace) -> None:
        self.workspace = workspace

    def read(self, agent_id: str) -> dict[str, Any]:
        return dict(self.workspace.private_context.get(agent_id, {}))

    def write(self, agent_id: str, payload: dict[str, Any]) -> None:
        self.workspace.private_context[agent_id] = dict(payload)

    def snapshot(self, agent_ids: list[str]) -> dict[str, dict[str, Any]]:
        return {agent_id: self.read(agent_id) for agent_id in agent_ids}


class V2MemoryManager:
    """Build governed context from shared and private memories."""

    def __init__(self, policy: V2MemoryPolicy | None = None) -> None:
        self.policy = policy or V2MemoryPolicy()

    def shared(self, workspace: SharedWorkspace) -> SharedMemory:
        return SharedMemory(workspace)

    def private(self, workspace: SharedWorkspace) -> PrivateMemory:
        return PrivateMemory(workspace)

    def build_agent_context(
        self,
        *,
        agent_id: str,
        workspace: SharedWorkspace,
    ) -> dict[str, Any]:
        shared = self.shared(workspace)
        private = self.private(workspace)
        selected = self._select_memory(agent_id=agent_id, shared=shared, private=private)
        selected["memory_policy"] = {
            "max_execution_notes": self.policy.max_execution_notes,
            "max_artifacts": self.policy.max_artifacts,
            "max_list_items": self.policy.max_list_items,
            "max_string_chars": self.policy.max_string_chars,
            "private_sources": self.policy.private_memory_by_agent.get(agent_id, []),
        }
        return self.trim_for_prompt(selected)

    def trim_for_prompt(self, value: Any) -> Any:
        return self._trim_value(value)

    def _select_memory(
        self,
        *,
        agent_id: str,
        shared: SharedMemory,
        private: PrivateMemory,
    ) -> dict[str, Any]:
        if agent_id == "planner":
            data = shared.snapshot(["current_plan", "latest_test_result", "project_summary"])
            data["orchestrator_context"] = private.read("orchestrator")
            return data
        if agent_id == "analyst":
            data = shared.snapshot(["project_summary", "artifacts_index", "current_plan"])
            data["artifacts_index"] = data["artifacts_index"][: self.policy.max_artifacts]
            data["analysis_context"] = private.read("analyst")
            return data
        if agent_id == "coder":
            data = shared.snapshot(["project_summary", "latest_test_result", "latest_patch_summary"])
            data["analysis_context"] = private.read("analyst")
            return data
        if agent_id == "external_coder":
            data = shared.snapshot(["project_summary", "latest_test_result", "latest_patch_summary"])
            data["analysis_context"] = private.read("analyst")
            data["orchestrator_context"] = private.read("orchestrator")
            return data
        if agent_id == "tester":
            data = shared.snapshot(["latest_patch_summary", "project_summary"])
            data["coder_context"] = private.read("coder")
            data["analysis_context"] = private.read("analyst")
            return data
        if agent_id == "reviewer":
            data = shared.snapshot(["project_summary", "latest_patch_summary", "latest_test_result"])
            data["coder_context"] = private.read("coder")
            data["analysis_context"] = private.read("analyst")
            data["reviewer_context"] = private.read("reviewer")
            return data
        return {}

    def _trim_value(self, value: Any) -> Any:
        if isinstance(value, str):
            if len(value) <= self.policy.max_string_chars:
                return value
            return f"{value[: self.policy.max_string_chars]}...<trimmed>"
        if isinstance(value, list):
            return [self._trim_value(item) for item in value[: self.policy.max_list_items]]
        if isinstance(value, dict):
            trimmed: dict[str, Any] = {}
            for index, key in enumerate(value):
                if index >= self.policy.max_dict_keys:
                    trimmed["<trimmed_keys>"] = len(value) - self.policy.max_dict_keys
                    break
                trimmed[str(key)] = self._trim_value(deepcopy(value[key]))
            return trimmed
        return deepcopy(value)
