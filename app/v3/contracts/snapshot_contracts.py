"""Snapshot contracts for V3.2 Phase 2."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class SnapshotType(str, Enum):
    """Types of snapshots."""

    WORKSPACE = "workspace"
    EXECUTION_STATE = "execution_state"
    EVENT_CHECKPOINT = "event_checkpoint"


class Snapshot(BaseModel):
    """A point-in-time snapshot for replay and debugging."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    snapshot_type: SnapshotType
    label: str = ""
    description: str = ""

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    workspace_metadata: dict[str, Any] = Field(default_factory=dict)
    execution_state: dict[str, Any] = Field(default_factory=dict)
    event_checkpoint: dict[str, Any] = Field(default_factory=dict)

    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkspaceSnapshotMetadata(BaseModel):
    """Metadata about a workspace snapshot."""

    model_config = ConfigDict(extra="forbid")

    root_path: str = ""
    file_count: int = 0
    total_size_bytes: int = 0
    modified_files: list[str] = Field(default_factory=list)
    created_files: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionStateSnapshot(BaseModel):
    """Snapshot of execution state at a point in time."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    completed_nodes: list[str] = Field(default_factory=list)
    failed_nodes: list[str] = Field(default_factory=list)
    pending_nodes: list[str] = Field(default_factory=list)
    shared_state_keys: list[str] = Field(default_factory=list)
    trigger_count: int = 0
    event_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class EventCheckpoint(BaseModel):
    """A checkpoint marker in the event stream."""

    model_config = ConfigDict(extra="forbid")

    checkpoint_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    event_count: int = 0
    last_event_id: str | None = None
    last_event_type: str | None = None
    chain_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
