"""Trigger contracts for V3."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TriggerRule(BaseModel):
    """A local event-to-skill trigger rule."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    event_type: str
    target_skill_name: str
    enabled: bool = True
    input_mapping: dict[str, Any] = Field(default_factory=dict)
