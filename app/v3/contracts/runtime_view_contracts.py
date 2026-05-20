"""User-facing runtime view contracts for V3 productization."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class V3RunModeView(BaseModel):
    """High-level label explaining which V3 runtime path was activated."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    description: str = ""


class V3FlowCardView(BaseModel):
    """One user-facing event -> trigger -> follow-up card."""

    model_config = ConfigDict(extra="forbid")

    event_type: str
    trigger_rule_id: str
    follow_up_label: str
    result_label: str
    governance_label: str
    stop_reason: str | None = None
    source_event_id: str | None = None
    summary: str = ""


class V3GovernanceExplainItem(BaseModel):
    """Readable governance explanation entry."""

    model_config = ConfigDict(extra="forbid")

    status: str
    label: str
    reason: str
    rule_id: str | None = None
    event_type: str | None = None
    detail: str = ""


class V3GovernanceSummary(BaseModel):
    """Aggregated governance statuses for one V3 run."""

    model_config = ConfigDict(extra="forbid")

    status_counts: dict[str, int] = Field(default_factory=dict)
    items: list[V3GovernanceExplainItem] = Field(default_factory=list)


class V3RuntimeSummary(BaseModel):
    """Product-facing V3 runtime summary for detail and autonomy views."""

    model_config = ConfigDict(extra="forbid")

    run_mode: V3RunModeView
    flow_cards: list[V3FlowCardView] = Field(default_factory=list)
    governance_summary: V3GovernanceSummary = Field(default_factory=V3GovernanceSummary)
    demo_scenarios: list[str] = Field(default_factory=list)
