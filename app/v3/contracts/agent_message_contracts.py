"""Minimal agent messaging contracts for V3 runtime coordination."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class AgentMessageType(str, Enum):
    """Supported runtime message directions."""

    REQUEST = "request"
    RESPONSE = "response"


class AgentMessage(BaseModel):
    """A lightweight runtime message between execution actors."""

    model_config = ConfigDict(extra="forbid")

    message_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    from_actor: str
    to_actor: str
    message_type: AgentMessageType
    node_id: str | None = None
    correlation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
