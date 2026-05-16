"""Scheduler contracts for V3.2 Phase 2."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(str, Enum):
    """Lifecycle states for a scheduled task."""

    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """Scheduling priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class TaskType(str, Enum):
    """Types of scheduled tasks."""

    DELAYED = "delayed"
    RECURRING = "recurring"
    INTERVAL = "interval"


class ScheduledTask(BaseModel):
    """A task managed by the V3.2 scheduler."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    task_type: TaskType
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING

    target_skill_name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""

    schedule_at: datetime | None = None
    interval_seconds: float | None = None
    max_repeats: int | None = None
    current_repeat: int = 0

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None

    last_error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_due(self) -> bool:
        if self.status not in (TaskStatus.PENDING, TaskStatus.SCHEDULED):
            return False
        if self.schedule_at is None:
            return True
        return datetime.now(UTC) >= self.schedule_at

    @property
    def can_repeat(self) -> bool:
        if self.task_type not in (TaskType.RECURRING, TaskType.INTERVAL):
            return False
        if self.max_repeats is None:
            return True
        return self.current_repeat < self.max_repeats
