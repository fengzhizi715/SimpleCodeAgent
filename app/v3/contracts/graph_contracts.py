"""Task graph contracts for V3."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TaskNodeStatus(str, Enum):
    """Lifecycle status for a task node."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskNode(BaseModel):
    """A node inside a V3 task graph."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    skill_name: str
    input_payload: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    status: TaskNodeStatus = TaskNodeStatus.PENDING


class TaskGraph(BaseModel):
    """A serial MVP task graph."""

    model_config = ConfigDict(extra="forbid")

    graph_id: str
    run_id: str
    nodes: list[TaskNode]


class GraphInspection(BaseModel):
    """Inspectable metadata for a validated V3 graph."""

    model_config = ConfigDict(extra="forbid")

    graph: TaskGraph
    is_valid: bool = True
    node_count: int
    edge_count: int
    root_node_ids: list[str] = Field(default_factory=list)
    leaf_node_ids: list[str] = Field(default_factory=list)
    execution_layers: list[list[str]] = Field(default_factory=list)
