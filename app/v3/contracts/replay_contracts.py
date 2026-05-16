"""Replay contracts for V3."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReplayMode(str, Enum):
    """Supported replay modes for V3.2."""

    TRACE_REPLAY = "trace_replay"
    EVENT_REPLAY = "event_replay"
    FIRST_ACTION_REPLAY = "first_action_replay"


class ReplayEntryType(str, Enum):
    """Entry points for replay."""

    BY_RUN = "by_run"
    BY_CHAIN = "by_chain"
    BY_EVENT = "by_event"


class ReplayMetadata(BaseModel):
    """Structured metadata for a simple V3 replay run."""

    model_config = ConfigDict(extra="forbid")

    replay_run_id: str
    source_run_id: str
    source_event_id: str
    execution_chain_id: str
    replay_mode: str = "event_chain"
    entry_type: str = "by_event"
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


class ReplayChainView(BaseModel):
    """Structured view of an event chain for trace replay."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    execution_chain_id: str
    root_event_id: str
    events: list[dict[str, Any]] = Field(default_factory=list)
    event_count: int = 0
    skill_events: list[dict[str, Any]] = Field(default_factory=list)
    trigger_events: list[dict[str, Any]] = Field(default_factory=list)


class ReplayPlan(BaseModel):
    """Plan for a replay run, listing available replay targets."""

    model_config = ConfigDict(extra="forbid")

    source_run_id: str
    entry_type: ReplayEntryType
    available_targets: list[dict[str, Any]] = Field(default_factory=list)
    chain_views: list[ReplayChainView] = Field(default_factory=list)
