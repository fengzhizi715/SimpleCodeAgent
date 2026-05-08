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
    priority: int = 100
    once_per_run: bool = False
    suppress_repeats: bool = False
    dedupe_key_template: str | None = None
    cooldown_key: str | None = None
    cooldown_seconds: float | None = None
    input_mapping: dict[str, Any] = Field(default_factory=dict)
