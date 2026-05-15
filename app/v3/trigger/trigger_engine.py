"""Trigger engine for V3."""

from __future__ import annotations

import time
from typing import Any

from app.v3.contracts.agent_message_contracts import AgentMessage, AgentMessageType
from app.v3.contracts.execution_contracts import ExecutionNode, TriggerDiagnostic
from app.v3.contracts.event_contracts import EventType, V3Event
from app.v3.contracts.skill_contracts import SkillInput
from app.v3.contracts.trigger_contracts import TriggerRule
from app.v3.events.event_bus import EventBus
from app.v3.events.event_store import EventStore
from app.v3.runtime.skill_executor import SkillExecutor
from app.v3.trigger.trigger_registry import TriggerRegistry

_TRIGGER_DEPTH_KEY = "__trigger_depth__"


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
        diagnostics: list[TriggerDiagnostic] | None = None,
        messages: list[AgentMessage] | None = None,
        max_triggers_per_run: int = 20,
        max_trigger_depth: int = 5,
    ) -> None:
        self.trigger_registry = trigger_registry
        self.skill_executor = skill_executor
        self.event_bus = event_bus
        self.event_store = event_store
        self.execution_nodes = execution_nodes
        self.diagnostics = diagnostics
        self.messages = messages
        self._fired_rule_runs: set[tuple[str, str]] = set()
        self._dedupe_keys_seen: set[tuple[str, str]] = set()
        self._cooldown_windows: dict[tuple[str, str], float] = {}
        self._total_fired_count: dict[str, int] = {}
        self._max_triggers_per_run = max_triggers_per_run
        self._max_trigger_depth = max_trigger_depth

    async def handle_event(self, event: V3Event) -> None:
        """Handle one published event."""
        run_id = event.run_id
        current_depth = int(event.payload.get(_TRIGGER_DEPTH_KEY, 0))

        if current_depth >= self._max_trigger_depth:
            self._record_diagnostic_for_event(
                event=event,
                status="skipped",
                skip_reason="max_depth_exceeded",
                metadata={"depth": current_depth, "max_depth": self._max_trigger_depth},
            )
            return

        total_count = self._total_fired_count.get(run_id, 0)
        if total_count >= self._max_triggers_per_run:
            self._record_diagnostic_for_event(
                event=event,
                status="skipped",
                skip_reason="max_triggers_per_run_exceeded",
                metadata={"total_count": total_count, "max_triggers": self._max_triggers_per_run},
            )
            return

        rules = self.trigger_registry.match(event.event_type)
        for rule in rules:
            if self._total_fired_count.get(run_id, 0) >= self._max_triggers_per_run:
                break

            skip_metadata = self._get_skip_metadata(rule, event)
            if skip_metadata is not None:
                self._record_diagnostic(
                    rule=rule,
                    event=event,
                    status="skipped",
                    metadata=skip_metadata,
                )
                await self._publish(
                    V3Event(
                        run_id=event.run_id,
                        event_type=EventType.TRIGGER_SKIPPED.value,
                        source=rule.target_skill_name,
                        payload={
                            "trigger_rule_id": rule.rule_id,
                            "source_event_type": event.event_type,
                            **skip_metadata,
                        },
                    )
                )
                continue
            payload = self._build_payload(rule.input_mapping, event)
            governance_metadata = self._build_governance_metadata(rule, event)
            request_message = self._record_message(
                AgentMessage(
                    run_id=event.run_id,
                    from_actor=f"trigger:{rule.rule_id}",
                    to_actor=rule.target_skill_name,
                    message_type=AgentMessageType.REQUEST,
                    node_id=str(event.payload.get("node_id") or "") or None,
                    payload={
                        "source_event_type": event.event_type,
                        "input_payload": payload,
                        "trigger_governance": governance_metadata,
                    },
                )
            )
            await self._publish(
                V3Event(
                    run_id=event.run_id,
                    event_type=EventType.SKILL_STARTED.value,
                    source=rule.target_skill_name,
                    payload={
                        "trigger_rule_id": rule.rule_id,
                        "source_event_type": event.event_type,
                        "input_payload": payload,
                        "trigger_governance": governance_metadata,
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
            self._total_fired_count[event.run_id] = self._total_fired_count.get(event.run_id, 0) + 1
            self._mark_fired(rule, event)
            self._record_diagnostic(
                rule=rule,
                event=event,
                status="executed",
                metadata=governance_metadata,
            )
            self._record_execution_node(
                event=event,
                rule=rule,
                rule_id=rule.rule_id,
                target_skill_name=rule.target_skill_name,
                output=output,
            )
            self._record_message(
                AgentMessage(
                    run_id=event.run_id,
                    from_actor=rule.target_skill_name,
                    to_actor=f"trigger:{rule.rule_id}",
                    message_type=AgentMessageType.RESPONSE,
                    node_id=str(event.payload.get("node_id") or "") or None,
                    correlation_id=request_message.message_id if request_message is not None else None,
                    payload={
                        "success": output.success,
                        "summary": output.summary,
                        "error": output.error,
                        "data": output.data,
                    },
                )
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
                        "trigger_governance": governance_metadata,
                    },
                )
            )

    def _record_message(self, message: AgentMessage) -> AgentMessage | None:
        if self.messages is None:
            return None
        self.messages.append(message)
        return message

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

    def _get_skip_metadata(self, rule: TriggerRule, event: V3Event) -> dict[str, object] | None:
        if rule.once_per_run and (event.run_id, rule.rule_id) in self._fired_rule_runs:
            metadata = self._build_governance_metadata(rule, event)
            metadata["skip_reason"] = "once_per_run"
            return metadata
        if self._is_in_cooldown(rule, event):
            metadata = self._build_governance_metadata(rule, event)
            metadata["skip_reason"] = "cooldown"
            return metadata
        if not rule.suppress_repeats:
            return None
        dedupe_key = self._build_dedupe_key(rule, event)
        if dedupe_key is None:
            dedupe_key = f"source_event:{event.event_id}"
        if (event.run_id, dedupe_key) in self._dedupe_keys_seen:
            metadata = self._build_governance_metadata(rule, event)
            metadata["skip_reason"] = "dedupe"
            return metadata
        return None

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

    def _build_governance_metadata(self, rule: TriggerRule, event: V3Event) -> dict[str, object]:
        return {
            "priority": rule.priority,
            "once_per_run": rule.once_per_run,
            "suppress_repeats": rule.suppress_repeats,
            "dedupe_key": self._build_dedupe_key(rule, event),
            "cooldown_key": self._build_cooldown_key(rule, event),
            "cooldown_seconds": rule.cooldown_seconds,
        }

    def _record_execution_node(
        self,
        *,
        event: V3Event,
        rule: TriggerRule,
        rule_id: str,
        target_skill_name: str,
        output,
    ) -> None:
        if self.execution_nodes is None:
            return
        output_data = dict(output.data)
        output_data["trigger_governance"] = self._build_governance_metadata(rule, event)
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
                recovery_on_success=rule.recovery_on_success,
                summary=output.summary,
                output_data=output_data,
            )
        )

    def _record_diagnostic(
        self,
        *,
        rule: TriggerRule,
        event: V3Event,
        status: str,
        metadata: dict[str, object],
    ) -> None:
        if self.diagnostics is None:
            return
        self.diagnostics.append(
            TriggerDiagnostic(
                trigger_rule_id=rule.rule_id,
                source_event_type=event.event_type,
                target_skill_name=rule.target_skill_name,
                status=status,
                skip_reason=str(metadata.get("skip_reason")) if metadata.get("skip_reason") is not None else None,
                dedupe_key=str(metadata.get("dedupe_key")) if metadata.get("dedupe_key") is not None else None,
                cooldown_key=str(metadata.get("cooldown_key")) if metadata.get("cooldown_key") is not None else None,
                cooldown_seconds=float(metadata["cooldown_seconds"]) if metadata.get("cooldown_seconds") is not None else None,
                priority=int(metadata["priority"]) if metadata.get("priority") is not None else None,
                once_per_run=bool(metadata["once_per_run"]) if metadata.get("once_per_run") is not None else None,
                suppress_repeats=bool(metadata["suppress_repeats"]) if metadata.get("suppress_repeats") is not None else None,
                source_event_id=event.event_id,
                parent_node_id=str(event.payload.get("node_id") or "") or None,
                details=dict(metadata),
            )
        )

    async def _publish(self, event: V3Event) -> None:
        payload = dict(event.payload)
        payload[_TRIGGER_DEPTH_KEY] = int(payload.get(_TRIGGER_DEPTH_KEY, 0)) + 1
        event = event.model_copy(update={"payload": payload})
        if self.event_store is not None:
            self.event_store.append(event)
        if self.event_bus is not None:
            await self.event_bus.publish(event)

    def _record_diagnostic_for_event(
        self,
        *,
        event: V3Event,
        status: str,
        skip_reason: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        """Record a diagnostic when a trigger is skipped due to governance limits."""
        if self.diagnostics is None:
            return
        self.diagnostics.append(
            TriggerDiagnostic(
                trigger_rule_id="__governance__",
                source_event_type=event.event_type,
                target_skill_name="__none__",
                status=status,
                skip_reason=skip_reason,
                source_event_id=event.event_id,
                parent_node_id=str(event.payload.get("node_id") or "") or None,
                details=dict(metadata or {}),
            )
        )
