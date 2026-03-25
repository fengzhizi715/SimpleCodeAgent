"""规划器协议定义。"""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

PlanStepStatus = Literal["pending", "in_progress", "completed", "failed"]


class PlanStep(BaseModel):
    """单个结构化规划步骤。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    description: str = ""
    status: PlanStepStatus = "pending"
    tool_name: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
