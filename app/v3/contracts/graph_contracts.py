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
