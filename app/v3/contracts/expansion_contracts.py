"""Dynamic expansion contracts for V3.2 Phase 2.

Supports limited, auditable execution expansion:
- Append virtual execution nodes at graph periphery
- Instantiate subgraph templates
- Append execution plan (not mutate original graph)
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.v3.contracts.graph_contracts import TaskGraph, TaskNode


class ExpansionType(str, Enum):
    """Types of dynamic expansion."""

    APPEND_VIRTUAL_NODE = "append_virtual_node"
    INSTANTIATE_SUBGRAPH = "instantiate_subgraph"
    APPEND_EXECUTION_PLAN = "append_execution_plan"


class ExpansionStatus(str, Enum):
    """Status of an expansion request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    FAILED = "failed"


class SubgraphTemplate(BaseModel):
    """A reusable subgraph template for instantiation."""

    model_config = ConfigDict(extra="forbid")

    template_id: str
    nodes: list[TaskNode]
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExpansionRequest(BaseModel):
    """Request to expand execution dynamically."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    expansion_type: ExpansionType
    reason: str
    source_node_id: str | None = None
    source_event_id: str | None = None

    virtual_node: TaskNode | None = None
    subgraph_template_id: str | None = None
    subgraph_template_data: SubgraphTemplate | None = None
    execution_plan: list[dict[str, Any]] = Field(default_factory=list)

    status: ExpansionStatus = ExpansionStatus.PENDING
    rejection_reason: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    applied_at: datetime | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


class ExpansionResult(BaseModel):
    """Result of applying an expansion."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    run_id: str
    success: bool
    appended_nodes: list[TaskNode] = Field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
