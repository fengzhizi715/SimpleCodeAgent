"""规划器协议定义。"""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

PlanStepStatus = Literal["pending", "in_progress", "completed", "failed"]
PlanStepType = Literal["analysis", "coding", "testing", "planning", "validation", "general"]
PlanStepExecutor = Literal["internal", "external"]


class PlanStep(BaseModel):
    """单个结构化规划步骤。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    goal: str = ""
    type: PlanStepType = "general"
    description: str = ""
    status: PlanStepStatus = "pending"
    suggested_agent: str | None = None
    input_requirements: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 0
    tool_name: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    strategy_explanation: str | None = None
    disabled_agent_adjustment: str | None = None
    replan_reason: str | None = None
    # 可选：验证步骤在 workspace 根目录下执行的 shell 命令（如 ./gradlew test、pytest tests/）
    verification_command: str | None = None
    # 可选：执行器选择。external 主要用于复杂 coding 任务委派给外部 Coding CLI。
    executor: PlanStepExecutor = "internal"
    # 当 executor=external 时，建议标记目标外部执行器（如 codex_cli / cursor_cli）。
    external_agent: str | None = None
    # 当 executor=external 时可显式给出命令模板（由 ExternalCodingAgent 通过 shell_run 执行）。
    external_command: str | None = None
    # 当 executor=external 时可选：给外部 Coding CLI 的任务描述（默认回退到 step goal）。
    external_prompt: str | None = None


class Plan(BaseModel):
    """结构化执行计划。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    summary: str = ""
    steps: list[PlanStep] = Field(default_factory=list)
    replan_count: int = 0
    metadata: dict[str, object] = Field(default_factory=dict)
