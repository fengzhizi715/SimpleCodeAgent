"""Execution reporting contracts for V3."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ExecutionStatus(str, Enum):
    """High-level graph execution status."""

    COMPLETED = "completed"
    PARTIAL_COMPLETED = "partial_completed"
    FAILED = "failed"


class ExecutionNode(BaseModel):
    """One execution unit in a V3 run.

    Graph nodes are first-class execution units.
    Trigger-driven follow-up skills are represented as virtual nodes.
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str
    kind: Literal["graph", "trigger"] = "graph"
    skill_name: str
    status: str
    dependencies: list[str] = Field(default_factory=list)
    source_event_type: str | None = None
    source_event_id: str | None = None
    trigger_rule_id: str | None = None
    parent_node_id: str | None = None
    summary: str = ""
    output_data: dict[str, Any] = Field(default_factory=dict)


class TriggerDiagnostic(BaseModel):
    """Lightweight diagnostic record for trigger execution or suppression."""

    model_config = ConfigDict(extra="forbid")

    trigger_rule_id: str
    source_event_type: str
    target_skill_name: str
    status: Literal["executed", "skipped"]
    skip_reason: str | None = None
    dedupe_key: str | None = None
    cooldown_key: str | None = None
    cooldown_seconds: float | None = None
    priority: int | None = None
    once_per_run: bool | None = None
    suppress_repeats: bool | None = None
    source_event_id: str | None = None
    parent_node_id: str | None = None


class ExecutionReport(BaseModel):
    """Serializable V3 execution report."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    graph_id: str
    status: ExecutionStatus
    completed_node_ids: list[str] = Field(default_factory=list)
    failed_node_ids: list[str] = Field(default_factory=list)
    recovered_node_ids: list[str] = Field(default_factory=list)
    skipped_node_ids: list[str] = Field(default_factory=list)
    node_outputs: dict[str, Any] = Field(default_factory=dict)
    shared_state: dict[str, Any] = Field(default_factory=dict)
    execution_nodes: list[ExecutionNode] = Field(default_factory=list)
    trigger_diagnostics: list[TriggerDiagnostic] = Field(default_factory=list)
