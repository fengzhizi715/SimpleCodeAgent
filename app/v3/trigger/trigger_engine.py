"""Trigger engine for V3 with V3.2 governance integration."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.v3.contracts.agent_message_contracts import AgentMessage, AgentMessageType
from app.v3.contracts.audit_contracts import StopReason
from app.v3.contracts.execution_contracts import ExecutionNode, TriggerDiagnostic
from app.v3.contracts.event_contracts import EventType, V3Event
from app.v3.contracts.skill_contracts import SkillInput
from app.v3.contracts.trigger_contracts import TriggerRule
from app.v3.events.event_bus import EventBus
from app.v3.events.event_store import EventStore
from app.v3.governance.circuit_breaker import CircuitBreakerManager
from app.v3.governance.execution_budget import ExecutionBudgetState
from app.v3.governance.propagation_limit import PropagationState
from app.v3.governance.trigger_guard import TriggerGuard
from app.v3.runtime.skill_executor import SkillExecutor
from app.v3.trigger.condition_evaluator import ConditionEvaluator
from app.v3.trigger.trigger_policy import build_governance_metadata
from app.v3.trigger.trigger_registry import TriggerRegistry

if TYPE_CHECKING:
    from app.v3.audit.audit_store import AuditLogStore

HitCallback = Callable[[str, str, str], None]

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
        trigger_guard: TriggerGuard | None = None,
        hit_callback: HitCallback | None = None,
        budget: ExecutionBudgetState | None = None,
        propagation: PropagationState | None = None,
        circuit_breaker: CircuitBreakerManager | None = None,
        audit_store: AuditLogStore | None = None,
    ) -> None:
        self.trigger_registry = trigger_registry
        self.skill_executor = skill_executor
        self.event_bus = event_bus
        self.event_store = event_store
        self.execution_nodes = execution_nodes
        self.diagnostics = diagnostics
        self.messages = messages
        self._hit_callback = hit_callback
        self._fired_rule_runs: set[tuple[str, str]] = set()
        self._dedupe_keys_seen: set[tuple[str, str]] = set()
        self._total_fired_count: dict[str, int] = {}
        self._rule_fired_count: dict[tuple[str, str], int] = {}
        self._max_triggers_per_run = max_triggers_per_run
        self._max_trigger_depth = max_trigger_depth
        self._guard = trigger_guard or TriggerGuard(condition_evaluator=ConditionEvaluator())
        self._budget = budget
        self._propagation = propagation
        self._circuit_breaker = circuit_breaker or CircuitBreakerManager()
        self.audit_store = audit_store
        self._stop_reasons: list[StopReason] = []

    @property
    def stop_reasons(self) -> list[StopReason]:
        return list(self._stop_reasons)

    async def handle_event(self, event: V3Event) -> None:
        """Handle one published event."""
        run_id = event.run_id
        current_depth = self._get_trigger_depth(event)

        if self._propagation is not None:
            self._propagation.set_depth(current_depth)
            if self._propagation.depth_exceeded:
                self._record_diagnostic_for_event(
                    event=event,
                    status="skipped",
                    skip_reason="propagation_depth_exceeded",
                    metadata={"depth": current_depth, "max_depth": self._propagation.max_depth},
                )
                return

        if current_depth >= self._max_trigger_depth:
            self._record_diagnostic_for_event(
                event=event,
                status="skipped",
                skip_reason="max_depth_exceeded",
                metadata={"depth": current_depth, "max_depth": self._max_trigger_depth},
            )
            return

        if self._budget is not None and self._budget.triggers_exhausted:
            self._record_diagnostic_for_event(
                event=event,
                status="skipped",
                skip_reason="budget_triggers_exhausted",
                metadata=self._budget.to_dict(),
            )
            return

        if self._budget is not None and self._budget.runtime_exhausted:
            self._record_diagnostic_for_event(
                event=event,
                status="skipped",
                skip_reason="budget_runtime_exhausted",
                metadata=self._budget.to_dict(),
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

            if self._budget is not None and self._budget.triggers_exhausted:
                break

            if self._circuit_breaker.is_open(rule.rule_id):
                self._record_diagnostic(
                    rule=rule,
                    event=event,
                    status="skipped",
                    metadata={
                        "skip_reason": "circuit_breaker_open",
                        "circuit_state": self._circuit_breaker.get_state(rule.rule_id),
                    },
                )
                continue

            if self._propagation is not None:
                consecutive_ok = self._propagation.record_rule_hit(rule.rule_id)
                if not consecutive_ok:
                    self._record_diagnostic(
                        rule=rule,
                        event=event,
                        status="skipped",
                        metadata={
                            "skip_reason": "max_consecutive_rule_hits",
                            "consecutive_hits": self._propagation.get_consecutive_hits(rule.rule_id),
                        },
                    )
                    continue

            skip_metadata = self._get_skip_metadata(rule, event)
            if skip_metadata is not None:
                if self._propagation is not None:
                    self._propagation.record_rule_miss(rule.rule_id)
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
                        metadata={
                            "governance_decision": {
                                **skip_metadata,
                                "rule_id": rule.rule_id,
                                "event_type": event.event_type,
                            },
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
                    correlation_id=request_message.message_id if request_message is not None else event.correlation_id,
                    parent_event_id=event.event_id,
                    trigger_rule_id=rule.rule_id,
                    execution_chain_id=self._resolve_execution_chain_id(event),
                    trigger_depth=current_depth,
                    payload={
                        "trigger_rule_id": rule.rule_id,
                        "source_event_type": event.event_type,
                        "input_payload": payload,
                        "trigger_governance": governance_metadata,
                    },
                    metadata={
                        "governance_decision": governance_metadata,
                    },
                )
            )

            if self._budget is not None:
                self._budget.consume_trigger()

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

            if output.success:
                self._circuit_breaker.record_success(rule.rule_id)
            else:
                self._circuit_breaker.record_failure(rule.rule_id, output.error)

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
                    correlation_id=request_message.message_id if request_message is not None else event.correlation_id,
                    parent_event_id=event.event_id,
                    trigger_rule_id=rule.rule_id,
                    execution_chain_id=self._resolve_execution_chain_id(event),
                    trigger_depth=current_depth,
                    payload={
                        "trigger_rule_id": rule.rule_id,
                        "source_event_type": event.event_type,
                        "summary": output.summary,
                        "error": output.error,
                        "data": output.data,
                        "trigger_governance": governance_metadata,
                    },
                    metadata={
                        "governance_decision": governance_metadata,
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
        dedupe_key = self._build_dedupe_key(rule, event)
        cooldown_key = self._build_cooldown_key(rule, event)
        skip_reason = self._guard.should_skip(
            rule=rule,
            event=event,
            fired_rule_runs=self._fired_rule_runs,
            dedupe_keys_seen=self._dedupe_keys_seen,
            rule_fired_count=self._rule_fired_count,
            dedupe_key=dedupe_key,
            cooldown_key=cooldown_key,
        )
        if skip_reason is None:
            return None
        metadata = self._build_governance_metadata(rule, event)
        metadata["skip_reason"] = skip_reason
        if skip_reason == "max_trigger_count_per_run":
            metadata["rule_count"] = self._rule_fired_count.get((event.run_id, rule.rule_id), 0)
        return metadata

    def _mark_fired(self, rule: TriggerRule, event: V3Event) -> None:
        self._guard.mark_fired(
            rule=rule,
            event=event,
            fired_rule_runs=self._fired_rule_runs,
            dedupe_keys_seen=self._dedupe_keys_seen,
            dedupe_key=self._build_dedupe_key(rule, event),
            cooldown_key=self._build_cooldown_key(rule, event),
            rule_fired_count=self._rule_fired_count,
        )

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
        return build_governance_metadata(
            rule=rule,
            event=event,
            dedupe_key=self._build_dedupe_key(rule, event),
            cooldown_key=self._build_cooldown_key(rule, event),
            rule_count=self._rule_fired_count.get((event.run_id, rule.rule_id), 0),
        )

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
        if status == "skipped":
            skip_reason = str(metadata.get("skip_reason")) if metadata.get("skip_reason") is not None else "unknown"
            stop_reason = StopReason(
                run_id=event.run_id,
                reason_type=skip_reason,
                actor="trigger_engine",
                summary=f"Trigger rule skipped: {skip_reason}",
                details=dict(metadata),
            )
            if self.audit_store is not None:
                self.audit_store.add_stop_reason(stop_reason)
            self._stop_reasons.append(stop_reason)
        if self._hit_callback is not None:
            self._hit_callback(event.run_id, rule.rule_id, status)

    async def _publish(self, event: V3Event) -> None:
        payload = dict(event.payload)
        next_depth = event.trigger_depth + 1
        payload[_TRIGGER_DEPTH_KEY] = next_depth
        event = event.model_copy(
            update={
                "payload": payload,
                "trigger_depth": next_depth,
                "execution_chain_id": event.execution_chain_id or event.parent_event_id or event.event_id,
            }
        )
        if self._budget is not None and not self._budget.consume_event():
            return
        if self.event_store is not None:
            self.event_store.append(event)
        if self.event_bus is not None:
            await self.event_bus.publish(event)

    @staticmethod
    def _get_trigger_depth(event: V3Event) -> int:
        return int(event.trigger_depth or event.payload.get(_TRIGGER_DEPTH_KEY, 0))

    @staticmethod
    def _resolve_execution_chain_id(event: V3Event) -> str:
        return event.execution_chain_id or event.parent_event_id or event.event_id

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
        if status == "skipped" and skip_reason is not None:
            stop_reason = StopReason(
                run_id=event.run_id,
                reason_type=skip_reason,
                actor="trigger_engine",
                summary=f"Trigger skipped: {skip_reason}",
                details=dict(metadata or {}),
            )
            if self.audit_store is not None:
                self.audit_store.add_stop_reason(stop_reason)
            self._stop_reasons.append(stop_reason)
