"""追踪协议定义。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class TraceEvent(BaseModel):
    """执行过程中产生的结构化追踪事件。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str | None = None
    session_id: str | None = None
    event_type: str
    message: str
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    payload: dict[str, Any] = Field(default_factory=dict)
