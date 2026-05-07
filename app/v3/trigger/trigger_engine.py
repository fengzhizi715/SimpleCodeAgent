"""Trigger engine for V3."""

from __future__ import annotations

from typing import Any

from app.v3.contracts.event_contracts import V3Event
from app.v3.contracts.skill_contracts import SkillInput
from app.v3.runtime.skill_executor import SkillExecutor
from app.v3.trigger.trigger_registry import TriggerRegistry


class TriggerEngine:
    """Fire skills in response to events."""

    def __init__(self, trigger_registry: TriggerRegistry, skill_executor: SkillExecutor) -> None:
        self.trigger_registry = trigger_registry
        self.skill_executor = skill_executor

    async def handle_event(self, event: V3Event) -> None:
        """Handle one published event."""
        rules = self.trigger_registry.match(event.event_type)
        for rule in rules:
            payload = self._build_payload(rule.input_mapping, event)
            await self.skill_executor.execute(
                rule.target_skill_name,
                SkillInput(
                    run_id=event.run_id,
                    payload=payload,
                    context={"source_event": event.model_dump(mode="json")},
                ),
            )

    def _build_payload(self, input_mapping: dict[str, Any], event: V3Event) -> dict[str, Any]:
        if not input_mapping:
            return dict(event.payload)

        resolved: dict[str, Any] = {}
        for key, value in input_mapping.items():
            if isinstance(value, str) and value.startswith("event.payload."):
                payload_key = value.removeprefix("event.payload.")
                resolved[key] = event.payload.get(payload_key)
                continue
            if value == "event.run_id":
                resolved[key] = event.run_id
                continue
            if value == "event.event_type":
                resolved[key] = event.event_type
                continue
            resolved[key] = value
        return resolved
