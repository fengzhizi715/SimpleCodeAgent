"""Runtime messaging contracts for V3.2 Phase 2."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class MessageStatus(str, Enum):
    """Lifecycle states for a runtime message."""

    QUEUED = "queued"
    DELAYED = "delayed"
    DELIVERED = "delivered"
    REJECTED = "rejected"
    EXPIRED = "expired"


class MessagePolicy(BaseModel):
    """Policy governing runtime message behavior."""

    model_config = ConfigDict(extra="forbid")

    max_rounds: int = 10
    allowed_targets: list[str] | None = None
    message_type_whitelist: list[str] | None = None
    max_delay_seconds: float = 300.0
    allow_self_message: bool = False


class RuntimeMessage(BaseModel):
    """A message in the runtime messaging system."""

    model_config = ConfigDict(extra="forbid")

    message_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    from_actor: str
    to_actor: str
    message_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: MessageStatus = MessageStatus.QUEUED
    round_number: int = 1
    correlation_id: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    deliver_at: datetime | None = None
    delivered_at: datetime | None = None
    rejected_reason: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_delayed(self) -> bool:
        if self.deliver_at is None:
            return False
        return datetime.now(UTC) < self.deliver_at

    @property
    def is_due(self) -> bool:
        if self.deliver_at is None:
            return True
        return datetime.now(UTC) >= self.deliver_at
