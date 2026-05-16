"""Autonomy contracts for V3.2 Controlled Autonomy."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AutonomyTaskType(str, Enum):
    """Types of autonomy-generated tasks."""

    FOLLOW_UP = "follow_up"
    SCHEDULED_CHECK = "scheduled_check"
    RETRY = "retry"
    SYSTEM_GENERATED = "system_generated"


class AutonomyRequest(BaseModel):
    """A controlled task request created by the autonomy runtime."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    run_id: str
    task_type: AutonomyTaskType
    target_skill_name: str
    reason: str
    source_event_id: str | None = None
    source_trigger_rule_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    max_iterations: int = 1
    stop_condition: str | None = None
    budget: AutonomyBudget | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AutonomyBudget(BaseModel):
    """Execution budget for an autonomy request."""

    model_config = ConfigDict(extra="forbid")

    max_steps: int = 10
    max_events: int = 20
    max_trigger_count: int = 5
    max_runtime_seconds: float = 300.0


class AutonomyDecision(BaseModel):
    """Governance decision for an autonomy request."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    run_id: str
    approved: bool
    reason: str
    policy_id: str | None = None
    applied_budget: AutonomyBudget | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
