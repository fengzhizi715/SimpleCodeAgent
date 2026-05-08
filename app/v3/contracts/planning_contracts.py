"""Planning contracts for V3."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.v3.contracts.graph_contracts import TaskGraph
from app.v3.contracts.trigger_contracts import TriggerRule


class RecoveryStrategy(str, Enum):
    """Supported recovery strategies for planner-generated graphs."""

    NONE = "none"
    FIX_ONLY = "fix_only"
    FIX_AND_RETEST = "fix_and_retest"


class PlanningResult(BaseModel):
    """Structured output from the V3 planning skill."""

    model_config = ConfigDict(extra="forbid")

    graph: TaskGraph
    repo_profile: str
    goal_kind: str
    recovery_strategy: RecoveryStrategy = RecoveryStrategy.NONE
    template_name: str = "default"
    template_reason: str = ""
    planner_notes: list[str] = Field(default_factory=list)
    candidate_test_commands: list[str] = Field(default_factory=list)
    candidate_test_targets: list[str] = Field(default_factory=list)
    trigger_rules: list[TriggerRule] = Field(default_factory=list)
