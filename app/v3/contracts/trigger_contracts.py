"""Trigger contracts for V3."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConditionOperator(str, Enum):
    """Supported condition operators for trigger matching."""

    EQ = "eq"
    IN = "in"
    EXISTS = "exists"


class ConditionSpec(BaseModel):
    """A small, structured condition used by trigger rules."""

    model_config = ConfigDict(extra="forbid")

    field: str
    op: ConditionOperator
    value: Any | None = None


class TriggerRule(BaseModel):
    """A local event-to-skill trigger rule."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    event_type: str
    target_skill_name: str
    enabled: bool = True
    recovery_on_success: bool = False
    priority: int = 100
    conditions: list[ConditionSpec] = Field(default_factory=list)
    once_per_run: bool = False
    suppress_repeats: bool = False
    dedupe_key_template: str | None = None
    cooldown_key: str | None = None
    cooldown_seconds: float | None = None
    max_trigger_count_per_run: int | None = None
    input_mapping: dict[str, Any] = Field(default_factory=dict)
