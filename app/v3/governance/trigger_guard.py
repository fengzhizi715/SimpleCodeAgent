"""Trigger governance checks for V3."""

from __future__ import annotations

from app.v3.contracts.event_contracts import V3Event
from app.v3.contracts.trigger_contracts import TriggerRule
from app.v3.governance.cooldown_manager import CooldownManager
from app.v3.trigger.condition_evaluator import ConditionEvaluator


class TriggerGuard:
    """Evaluate runtime governance conditions for one trigger rule."""

    def __init__(
        self,
        *,
        condition_evaluator: ConditionEvaluator | None = None,
        cooldown_manager: CooldownManager | None = None,
    ) -> None:
        self.condition_evaluator = condition_evaluator or ConditionEvaluator()
        self.cooldown_manager = cooldown_manager or CooldownManager()

    def should_skip(
        self,
        *,
        rule: TriggerRule,
        event: V3Event,
        fired_rule_runs: set[tuple[str, str]],
        dedupe_keys_seen: set[tuple[str, str]],
        rule_fired_count: dict[tuple[str, str], int],
        dedupe_key: str | None,
        cooldown_key: str | None,
    ) -> str | None:
        """Return a skip reason when the trigger should not fire."""
        if not self.condition_evaluator.matches(rule.conditions, event):
            return "conditions_not_met"
        if rule.once_per_run and (event.run_id, rule.rule_id) in fired_rule_runs:
            return "once_per_run"
        current_rule_count = rule_fired_count.get((event.run_id, rule.rule_id), 0)
        if rule.max_trigger_count_per_run is not None and current_rule_count >= rule.max_trigger_count_per_run:
            return "max_trigger_count_per_run"
        resolved_cooldown_key = cooldown_key or f"{rule.rule_id}:event_type:{event.event_type}"
        if self.cooldown_manager.is_in_cooldown(
            run_id=event.run_id,
            cooldown_key=resolved_cooldown_key,
            cooldown_seconds=rule.cooldown_seconds,
        ):
            return "cooldown"
        if rule.suppress_repeats:
            resolved_dedupe_key = dedupe_key or f"source_event:{event.event_id}"
            if (event.run_id, resolved_dedupe_key) in dedupe_keys_seen:
                return "dedupe"
        return None

    def mark_fired(
        self,
        *,
        rule: TriggerRule,
        event: V3Event,
        fired_rule_runs: set[tuple[str, str]],
        dedupe_keys_seen: set[tuple[str, str]],
        dedupe_key: str | None,
        cooldown_key: str | None,
        rule_fired_count: dict[tuple[str, str], int],
    ) -> None:
        """Update governance state after one trigger execution."""
        if rule.once_per_run:
            fired_rule_runs.add((event.run_id, rule.rule_id))
        rule_fired_count[(event.run_id, rule.rule_id)] = rule_fired_count.get((event.run_id, rule.rule_id), 0) + 1
        self.cooldown_manager.mark(
            run_id=event.run_id,
            cooldown_key=cooldown_key or f"{rule.rule_id}:event_type:{event.event_type}",
            cooldown_seconds=rule.cooldown_seconds,
        )
        if rule.suppress_repeats:
            dedupe_keys_seen.add((event.run_id, dedupe_key or f"source_event:{event.event_id}"))
