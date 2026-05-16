"""Replay contracts for V3."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReplayMetadata(BaseModel):
    """Structured metadata for a simple V3 replay run."""

    model_config = ConfigDict(extra="forbid")

    replay_run_id: str
    source_run_id: str
    source_event_id: str
    execution_chain_id: str
    replay_mode: str = "event_chain"
    target_skill_name: str


class ReplayResult(BaseModel):
    """Serializable result for one simple V3 replay execution."""

    model_config = ConfigDict(extra="forbid")

    metadata: ReplayMetadata
    success: bool
    summary: str
    error: str | None = None
    output: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
