"""Event contracts for V3."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class EventType(str, Enum):
    """Supported V3 event types."""

    GRAPH_STARTED = "graph_started"
    GRAPH_FINISHED = "graph_finished"
    SKILL_STARTED = "skill_started"
    SKILL_FINISHED = "skill_finished"
    SKILL_FAILED = "skill_failed"
    SKILL_SKIPPED = "skill_skipped"
    TRIGGER_SKIPPED = "trigger_skipped"
    TEST_STARTED = "test_started"
    TEST_PASSED = "test_passed"
    TEST_FAILED = "test_failed"
    CODE_UPDATED = "code_updated"


class V3Event(BaseModel):
    """A local V3 event.

    ``metadata`` is the recommended place for V3.2 infrastructure annotations:
    - governance decision
    - autonomy origin
    - replay marker
    - schedule marker
    - audit tags

    Use ``payload`` for domain / user-visible data instead.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    event_type: str
    source: str
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    parent_event_id: str | None = None
    trigger_rule_id: str | None = None
    execution_chain_id: str | None = None
    trigger_depth: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)
