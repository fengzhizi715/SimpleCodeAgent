"""Trigger registry for V3."""

from __future__ import annotations

from app.v3.contracts.trigger_contracts import TriggerRule


class TriggerRegistry:
    """Store local trigger rules."""

    def __init__(self) -> None:
        self._rules: list[TriggerRule] = []

    def register(self, rule: TriggerRule) -> None:
        """Register a trigger rule."""
        self._rules.append(rule)

    def match(self, event_type: str) -> list[TriggerRule]:
        """Match enabled rules by event type."""
        return sorted(
            [rule for rule in self._rules if rule.enabled and rule.event_type == event_type],
            key=lambda rule: (rule.priority, rule.rule_id),
        )
