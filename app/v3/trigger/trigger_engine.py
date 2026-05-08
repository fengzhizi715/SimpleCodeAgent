"""Trigger engine for V3."""

from __future__ import annotations

import time
from typing import Any

from app.v3.contracts.execution_contracts import ExecutionNode
from app.v3.contracts.event_contracts import EventType, V3Event
from app.v3.contracts.skill_contracts import SkillInput
from app.v3.contracts.trigger_contracts import TriggerRule
from app.v3.events.event_bus import EventBus
from app.v3.events.event_store import EventStore
from app.v3.runtime.skill_executor import SkillExecutor
from app.v3.trigger.trigger_registry import TriggerRegistry


class TriggerEngine:
    """Fire skills in response to events."""

    def __init__(
        self,
        trigger_registry: TriggerRegistry,
        skill_executor: SkillExecutor,
        *,
        event_bus: EventBus | None = None,
        event_store: EventStore | None = None,
        execution_nodes: list[ExecutionNode] | None = None,
    ) -> None:
        self.trigger_registry = trigger_registry
        self.skill_executor = skill_executor
        self.event_bus = event_bus
        self.event_store = event_store
        self.execution_nodes = execution_nodes
        self._fired_rule_runs: set[tuple[str, str]] = set()
        self._dedupe_keys_seen: set[tuple[str, str]] = set()
        self._cooldown_windows: dict[tuple[str, str], float] = {}

    async def handle_event(self, event: V3Event) -> None:
        """Handle one published event."""
        rules = self.trigger_registry.match(event.event_type)
        for rule in rules:
            if self._should_skip(rule, event):
                continue
            payload = self._build_payload(rule.input_mapping, event)
            await self._publish(
                V3Event(
                    run_id=event.run_id,
                    event_type=EventType.SKILL_STARTED.value,
                    source=rule.target_skill_name,
                    payload={
                        "trigger_rule_id": rule.rule_id,
                        "source_event_type": event.event_type,
                        "input_payload": payload,
                    },
                )
            )
            output = await self.skill_executor.execute(
                rule.target_skill_name,
                SkillInput(
                    run_id=event.run_id,
                    payload=payload,
                    context={"source_event": event.model_dump(mode="json")},
                ),
            )
            self._mark_fired(rule, event)
            self._record_execution_node(
                event=event,
                rule_id=rule.rule_id,
                target_skill_name=rule.target_skill_name,
                output=output,
            )
            await self._publish(
                V3Event(
                    run_id=event.run_id,
                    event_type=(
                        EventType.SKILL_FINISHED.value if output.success else EventType.SKILL_FAILED.value
                    ),
                    source=rule.target_skill_name,
                    payload={
                        "trigger_rule_id": rule.rule_id,
                        "source_event_type": event.event_type,
                        "summary": output.summary,
                        "error": output.error,
                        "data": output.data,
                    },
                )
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

    def _should_skip(self, rule: TriggerRule, event: V3Event) -> bool:
        if rule.once_per_run and (event.run_id, rule.rule_id) in self._fired_rule_runs:
            return True
        if self._is_in_cooldown(rule, event):
            return True
        if not rule.suppress_repeats:
            return False
        dedupe_key = self._build_dedupe_key(rule, event)
        if dedupe_key is None:
            dedupe_key = f"source_event:{event.event_id}"
        return (event.run_id, dedupe_key) in self._dedupe_keys_seen

    def _mark_fired(self, rule: TriggerRule, event: V3Event) -> None:
        if rule.once_per_run:
            self._fired_rule_runs.add((event.run_id, rule.rule_id))
        self._mark_cooldown(rule, event)
        if rule.suppress_repeats:
            dedupe_key = self._build_dedupe_key(rule, event)
            if dedupe_key is None:
                dedupe_key = f"source_event:{event.event_id}"
            self._dedupe_keys_seen.add((event.run_id, dedupe_key))

    def _build_dedupe_key(self, rule: TriggerRule, event: V3Event) -> str | None:
        template = rule.dedupe_key_template
        if not template:
            return None
        resolved = self._resolve_template_value(template, event)
        return None if resolved is None else f"{rule.rule_id}:{resolved}"

    def _build_cooldown_key(self, rule: TriggerRule, event: V3Event) -> str | None:
        template = rule.cooldown_key
        if not template:
            return None
        resolved = self._resolve_template_value(template, event)
        return None if resolved is None else f"{rule.rule_id}:{resolved}"

    def _is_in_cooldown(self, rule: TriggerRule, event: V3Event) -> bool:
        if rule.cooldown_seconds is None or rule.cooldown_seconds <= 0:
            return False
        cooldown_key = self._build_cooldown_key(rule, event)
        if cooldown_key is None:
            cooldown_key = f"{rule.rule_id}:event_type:{event.event_type}"
        last_fired_at = self._cooldown_windows.get((event.run_id, cooldown_key))
        if last_fired_at is None:
            return False
        return (time.monotonic() - last_fired_at) < rule.cooldown_seconds

    def _mark_cooldown(self, rule: TriggerRule, event: V3Event) -> None:
        if rule.cooldown_seconds is None or rule.cooldown_seconds <= 0:
            return
        cooldown_key = self._build_cooldown_key(rule, event)
        if cooldown_key is None:
            cooldown_key = f"{rule.rule_id}:event_type:{event.event_type}"
        self._cooldown_windows[(event.run_id, cooldown_key)] = time.monotonic()

    def _resolve_template_value(self, value: Any, event: V3Event) -> Any:
        if isinstance(value, str) and value.startswith("event.payload."):
            payload_key = value.removeprefix("event.payload.")
            return event.payload.get(payload_key)
        if value == "event.run_id":
            return event.run_id
        if value == "event.event_type":
            return event.event_type
        if value == "event.source":
            return event.source
        return value

    def _record_execution_node(
        self,
        *,
        event: V3Event,
        rule_id: str,
        target_skill_name: str,
        output,
    ) -> None:
        if self.execution_nodes is None:
            return
        self.execution_nodes.append(
            ExecutionNode(
                node_id=f"trigger:{rule_id}:{event.event_id}",
                kind="trigger",
                skill_name=target_skill_name,
                status="done" if output.success else "failed",
                source_event_type=event.event_type,
                source_event_id=event.event_id,
                trigger_rule_id=rule_id,
                parent_node_id=str(event.payload.get("node_id") or "") or None,
                summary=output.summary,
                output_data=dict(output.data),
            )
        )

    async def _publish(self, event: V3Event) -> None:
        if self.event_store is not None:
            self.event_store.append(event)
        if self.event_bus is not None:
            await self.event_bus.publish(event)
