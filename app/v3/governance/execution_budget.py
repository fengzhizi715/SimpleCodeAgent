"""Execution budget tracking for V3.2 Controlled Autonomy."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class ExecutionBudgetState:
    """Mutable budget state for a single run."""

    run_id: str
    max_steps: int = 100
    max_events: int = 200
    max_trigger_count: int = 20
    max_runtime_seconds: float = 600.0

    steps_used: int = 0
    events_used: int = 0
    trigger_count: int = 0
    start_time: float = field(default_factory=time.monotonic)

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.start_time

    @property
    def runtime_exhausted(self) -> bool:
        return self.elapsed_seconds >= self.max_runtime_seconds

    @property
    def steps_exhausted(self) -> bool:
        return self.steps_used >= self.max_steps

    @property
    def events_exhausted(self) -> bool:
        return self.events_used >= self.max_events

    @property
    def triggers_exhausted(self) -> bool:
        return self.trigger_count >= self.max_trigger_count

    @property
    def any_exhausted(self) -> bool:
        return (
            self.runtime_exhausted
            or self.steps_exhausted
            or self.events_exhausted
            or self.triggers_exhausted
        )

    def get_exhaustion_reasons(self) -> list[str]:
        reasons: list[str] = []
        if self.runtime_exhausted:
            reasons.append(
                f"runtime_exhausted: {self.elapsed_seconds:.1f}s >= {self.max_runtime_seconds}s"
            )
        if self.steps_exhausted:
            reasons.append(
                f"steps_exhausted: {self.steps_used} >= {self.max_steps}"
            )
        if self.events_exhausted:
            reasons.append(
                f"events_exhausted: {self.events_used} >= {self.max_events}"
            )
        if self.triggers_exhausted:
            reasons.append(
                f"triggers_exhausted: {self.trigger_count} >= {self.max_trigger_count}"
            )
        return reasons

    def consume_step(self) -> bool:
        if self.steps_exhausted:
            return False
        self.steps_used += 1
        return True

    def consume_event(self) -> bool:
        if self.events_exhausted:
            return False
        self.events_used += 1
        return True

    def consume_trigger(self) -> bool:
        if self.triggers_exhausted:
            return False
        self.trigger_count += 1
        return True

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "max_steps": self.max_steps,
            "max_events": self.max_events,
            "max_trigger_count": self.max_trigger_count,
            "max_runtime_seconds": self.max_runtime_seconds,
            "steps_used": self.steps_used,
            "events_used": self.events_used,
            "trigger_count": self.trigger_count,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "runtime_exhausted": self.runtime_exhausted,
            "steps_exhausted": self.steps_exhausted,
            "events_exhausted": self.events_exhausted,
            "triggers_exhausted": self.triggers_exhausted,
        }
