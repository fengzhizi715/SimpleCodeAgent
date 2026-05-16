"""Skill contracts for V3."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SkillType(str, Enum):
    """Supported V3 skill types."""

    TOOL = "tool"
    AGENT = "agent"
    COMPOSITE = "composite"


class SkillSpec(BaseModel):
    """Static metadata for a skill."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    skill_type: SkillType
    capabilities: list[str] = Field(default_factory=list)
    enabled: bool = True
    consumes_events: list[str] = Field(default_factory=list)
    emits_events: list[str] = Field(default_factory=list)
    retryable: bool = False
    cooldown_seconds: float | None = None
    timeout_seconds: int | None = None
    typical_use: str = ""
    template_names: list[str] = Field(default_factory=list)


class SkillInput(BaseModel):
    """Execution input for a skill."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class SkillOutput(BaseModel):
    """Execution output for a skill."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    summary: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
