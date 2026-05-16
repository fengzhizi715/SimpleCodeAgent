"""Audit contracts for V3.2 Controlled Autonomy."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class AuditAction(str, Enum):
    """Types of audit actions."""

    AUTONOMY_REQUEST_CREATED = "autonomy_request_created"
    AUTONOMY_REQUEST_APPROVED = "autonomy_request_approved"
    AUTONOMY_REQUEST_REJECTED = "autonomy_request_rejected"
    BUDGET_EXHAUSTED = "budget_exhausted"
    PROPAGATION_LIMIT_REACHED = "propagation_limit_reached"
    CIRCUIT_BREAKER_OPENED = "circuit_breaker_opened"
    CIRCUIT_BREAKER_CLOSED = "circuit_breaker_closed"
    TASK_CREATED = "task_created"
    TASK_EXECUTED = "task_executed"
    TASK_STOPPED = "task_stopped"
    GOVERNANCE_INTERCEPTED = "governance_intercepted"


class AuditRecord(BaseModel):
    """A single audit log entry."""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    event_id: str | None = None
    execution_chain_id: str | None = None
    policy_id: str | None = None
    rule_id: str | None = None
    action: AuditAction
    actor: str
    target: str
    reason: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DecisionTrace(BaseModel):
    """Structured trace of why a governance decision was made."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    event_id: str | None = None
    execution_chain_id: str | None = None
    decision_type: str
    approved: bool
    reason: str
    factors: list[dict[str, Any]] = Field(default_factory=list)
    summary: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GovernanceAction(BaseModel):
    """A governance action taken by the runtime."""

    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    action_type: str
    target_id: str
    target_type: str
    reason: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StopReason(BaseModel):
    """Structured reason why execution was stopped.

    ``reason_type`` uses a fixed vocabulary:
    - budget_exhausted
    - propagation_limit
    - circuit_breaker_open
    - governance_rejected
    - user_cancelled
    - error

    ``details`` carries per-reason-type diagnostics (e.g. budget counters).
    """

    model_config = ConfigDict(extra="forbid")

    stop_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    event_id: str | None = None
    execution_chain_id: str | None = None
    reason_type: str
    actor: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
