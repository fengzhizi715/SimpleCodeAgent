"""规划器协议定义。"""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

PlanStepStatus = Literal["pending", "in_progress", "completed", "failed"]
PlanStepType = Literal["analysis", "coding", "testing", "planning", "validation", "general"]


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


class Plan(BaseModel):
    """结构化执行计划。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    summary: str = ""
    steps: list[PlanStep] = Field(default_factory=list)
    replan_count: int = 0
