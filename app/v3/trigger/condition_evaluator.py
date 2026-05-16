"""Structured condition evaluation for V3 trigger rules."""

from __future__ import annotations

from typing import Any

from app.v3.contracts.event_contracts import V3Event
from app.v3.contracts.trigger_contracts import ConditionOperator, ConditionSpec


class ConditionEvaluator:
    """Evaluate structured trigger conditions against one event."""

    def matches(self, conditions: list[ConditionSpec], event: V3Event) -> bool:
        """Return True when every condition matches the event."""
        for condition in conditions:
            value = self.resolve_field(condition.field, event)
            if condition.op == ConditionOperator.EXISTS:
                if value is None:
                    return False
                continue
            if condition.op == ConditionOperator.EQ:
                if value != condition.value:
                    return False
                continue
            if condition.op == ConditionOperator.IN:
                if not isinstance(condition.value, (list, tuple, set)):
                    return False
                if value not in condition.value:
                    return False
                continue
            return False
        return True

    def resolve_field(self, field: str, event: V3Event) -> Any:
        """Resolve one limited event field path."""
        if field == "event.run_id":
            return event.run_id
        if field == "event.event_type":
            return event.event_type
        if field == "event.source":
            return event.source
        if field == "event.correlation_id":
            return event.correlation_id
        if field.startswith("event.payload."):
            current: Any = event.payload
            for part in field.removeprefix("event.payload.").split("."):
                if not isinstance(current, dict):
                    return None
                current = current.get(part)
            return current
        return None
