"""Execution reporting contracts for V3."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecutionStatus(str, Enum):
    """High-level graph execution status."""

    COMPLETED = "completed"
    PARTIAL_COMPLETED = "partial_completed"
    FAILED = "failed"


class ExecutionReport(BaseModel):
    """Serializable V3 execution report."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    graph_id: str
    status: ExecutionStatus
    completed_node_ids: list[str] = Field(default_factory=list)
    failed_node_ids: list[str] = Field(default_factory=list)
    skipped_node_ids: list[str] = Field(default_factory=list)
    node_outputs: dict[str, Any] = Field(default_factory=dict)
    shared_state: dict[str, Any] = Field(default_factory=dict)
