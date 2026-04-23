"""V2 多 Agent 协议定义。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.planner import Plan
from app.contracts.run import RunMetrics, RunUsage

AgentAvailability = Literal["enabled", "disabled"]
AgentTaskStatus = Literal["pending", "running", "completed", "failed"]
AgentResultStatus = Literal["completed", "failed", "retryable", "needs_replan"]


class AgentSpec(BaseModel):
    """系统内可注册 Agent 的定义。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    agent_id: str
    role: str
    description: str
    capabilities: list[str] = Field(default_factory=list)
    availability: AgentAvailability = "enabled"


class AgentArtifact(BaseModel):
    """Agent 产出的结构化工件摘要。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    artifact_id: str = Field(default_factory=lambda: str(uuid4()))
    key: str
    type: str
    summary: str
    version: int = 1
    producer_agent: str | None = None
    content: dict[str, Any] = Field(default_factory=dict)


class AgentTask(BaseModel):
    """Orchestrator 下发给子 Agent 的结构化任务。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    run_id: str
    step_id: str | None = None
    goal: str
    step_type: str = "general"
    target_agent: str
    input_data: dict[str, Any] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 0
    parent_task_id: str | None = None


class TestReport(BaseModel):
    """Tester Agent 输出的结构化测试报告。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    __test__ = False

    status: Literal["passed", "failed", "blocked"]
    executed_command: str
    summary: str
    failure_type: str | None = None
    key_logs: list[str] = Field(default_factory=list)
    suggested_next_action: str | None = None


class AgentResult(BaseModel):
    """Agent 执行结果。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task_id: str
    agent_id: str
    status: AgentResultStatus
    summary: str
    output_data: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[AgentArtifact] = Field(default_factory=list)
    usage: RunUsage | None = None
    metrics: RunMetrics | None = None
    error_message: str | None = None
    next_action: str | None = None


class DelegationRecord(BaseModel):
    """单次委派记录。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    delegation_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    session_id: str
    step_id: str | None = None
    parent_agent_id: str
    target_agent: str
    task_id: str
    status: AgentTaskStatus = "pending"
    summary: str = ""
    error_message: str | None = None
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None


class WorkspaceArtifactIndex(BaseModel):
    """Shared Workspace 中记录的工件索引项。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    key: str
    type: str
    summary: str
    latest_artifact_id: str | None = None
    version: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewIssue(BaseModel):
    """Reviewer Agent 发现的问题或风险。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    severity: Literal["low", "medium", "high"]
    title: str
    detail: str
    file_path: str | None = None


class SharedWorkspace(BaseModel):
    """多 Agent 共享状态中心。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    session_id: str
    run_id: str
    user_goal: str
    current_plan: Plan | None = None
    project_summary: str = ""
    latest_patch_summary: str = ""
    latest_test_result: TestReport | None = None
    artifacts_index: list[WorkspaceArtifactIndex] = Field(default_factory=list)
    execution_notes: list[str] = Field(default_factory=list)
    private_context: dict[str, dict[str, Any]] = Field(default_factory=dict)
