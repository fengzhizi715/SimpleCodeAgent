"""Helpers for building trigger governance metadata."""

from __future__ import annotations

from app.v3.contracts.event_contracts import V3Event
from app.v3.contracts.trigger_contracts import TriggerRule


def build_governance_metadata(
    *,
    rule: TriggerRule,
    event: V3Event,
    dedupe_key: str | None,
    cooldown_key: str | None,
    rule_count: int,
) -> dict[str, object]:
    """Build a stable governance metadata payload for trace/report/UI."""
    return {
        "priority": rule.priority,
        "conditions": [condition.model_dump(mode="json") for condition in rule.conditions],
        "once_per_run": rule.once_per_run,
        "suppress_repeats": rule.suppress_repeats,
        "dedupe_key": dedupe_key,
        "cooldown_key": cooldown_key,
        "cooldown_seconds": rule.cooldown_seconds,
        "rule_count": rule_count,
        "max_trigger_count_per_run": rule.max_trigger_count_per_run,
        "event_type": event.event_type,
    }
