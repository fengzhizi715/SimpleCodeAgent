"""Structured payload models and constants for V2 agents."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.planner import PlanStepType

PLANNER_TOOL_HINTS: dict[str, str] = {
    "analysis": "file_search",
    "coding": "write_file",
    "testing": "shell_run",
    "planning": None,  # type: ignore[assignment]
    "validation": "shell_run",
    "general": None,  # type: ignore[assignment]
}


class PlannerStepPayload(BaseModel):
    """LLM planner output schema for one step."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str
    goal: str
    type: PlanStepType = "general"
    description: str = ""
    suggested_agent: Literal["analyst", "coder", "tester"] = "coder"
    input_requirements: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    max_retries: int = 1
    verification_command: str | None = None
    executor: Literal["internal", "external"] = "internal"
    external_agent: str | None = None
    external_command: str | None = None
    external_prompt: str | None = None


class PlannerOutputPayload(BaseModel):
    """LLM planner output schema."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    summary: str
    steps: list[PlannerStepPayload]


class AnalysisFilePayload(BaseModel):
    """Structured key file entry from analyst."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    path: str
    reason: str


class AnalystOutputPayload(BaseModel):
    """Analyst structured output schema."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    project_summary: str
    module_responsibilities: dict[str, str] = Field(default_factory=dict)
    entry_files: list[str] = Field(default_factory=list)
    key_files: list[AnalysisFilePayload] = Field(default_factory=list)
    coding_hints: list[str] = Field(default_factory=list)


class ReviewIssuePayload(BaseModel):
    """LLM reviewer issue schema."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    severity: Literal["low", "medium", "high"]
    title: str
    detail: str
    file_path: str | None = None


class ReviewOutputPayload(BaseModel):
    """LLM reviewer output schema."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    review_summary: str
    issues: list[ReviewIssuePayload] = Field(default_factory=list)
    recommended_action: str = ""
