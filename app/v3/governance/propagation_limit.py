"""Propagation limit tracking for V3.2 Controlled Autonomy."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PropagationState:
    """Tracks propagation limits for a single run."""

    run_id: str
    max_depth: int = 5
    max_autonomy_tasks_per_run: int = 10
    max_consecutive_rule_hits: int = 5

    current_depth: int = 0
    autonomy_task_count: int = 0
    consecutive_rule_hits: dict[str, int] = field(default_factory=dict)

    @property
    def depth_exceeded(self) -> bool:
        return self.current_depth >= self.max_depth

    @property
    def autonomy_tasks_exceeded(self) -> bool:
        return self.autonomy_task_count >= self.max_autonomy_tasks_per_run

    def get_consecutive_hits(self, rule_id: str) -> int:
        return self.consecutive_rule_hits.get(rule_id, 0)

    def record_rule_hit(self, rule_id: str) -> bool:
        current = self.consecutive_rule_hits.get(rule_id, 0)
        self.consecutive_rule_hits[rule_id] = current + 1
        return self.consecutive_rule_hits[rule_id] <= self.max_consecutive_rule_hits

    def record_rule_miss(self, rule_id: str) -> None:
        self.consecutive_rule_hits.pop(rule_id, None)

    def consume_autonomy_task(self) -> bool:
        self.autonomy_task_count += 1
        return not self.autonomy_tasks_exceeded

    def set_depth(self, depth: int) -> bool:
        self.current_depth = depth
        return not self.depth_exceeded

    def get_exhaustion_reasons(self) -> list[str]:
        reasons: list[str] = []
        if self.depth_exceeded:
            reasons.append(
                f"depth_exceeded: {self.current_depth} >= {self.max_depth}"
            )
        if self.autonomy_tasks_exceeded:
            reasons.append(
                f"autonomy_tasks_exceeded: {self.autonomy_task_count} >= {self.max_autonomy_tasks_per_run}"
            )
        over_limit_rules = [
            f"{rule_id}: {count} >= {self.max_consecutive_rule_hits}"
            for rule_id, count in self.consecutive_rule_hits.items()
            if count >= self.max_consecutive_rule_hits
        ]
        if over_limit_rules:
            reasons.append(f"consecutive_rule_hits: {', '.join(over_limit_rules)}")
        return reasons

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "max_depth": self.max_depth,
            "max_autonomy_tasks_per_run": self.max_autonomy_tasks_per_run,
            "max_consecutive_rule_hits": self.max_consecutive_rule_hits,
            "current_depth": self.current_depth,
            "autonomy_task_count": self.autonomy_task_count,
            "consecutive_rule_hits": dict(self.consecutive_rule_hits),
        }
