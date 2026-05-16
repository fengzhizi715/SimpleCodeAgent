"""Circuit breaker for V3.2 Controlled Autonomy."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerEntry:
    """State for a single circuit breaker."""

    target_id: str
    target_type: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    failure_threshold: int = 3
    recovery_timeout_seconds: float = 60.0
    last_failure_at: float | None = None
    last_state_change_at: float = field(default_factory=time.monotonic)
    open_reason: str | None = None

    @property
    def is_open(self) -> bool:
        if self.state != CircuitState.OPEN:
            return False
        if self.last_failure_at is None:
            return False
        elapsed = time.monotonic() - self.last_failure_at
        if elapsed >= self.recovery_timeout_seconds:
            self.state = CircuitState.HALF_OPEN
            self.last_state_change_at = time.monotonic()
            return False
        return True

    def record_success(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_state_change_at = time.monotonic()
        self.success_count += 1

    def record_failure(self, reason: str | None = None) -> None:
        self.failure_count += 1
        self.last_failure_at = time.monotonic()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.open_reason = reason or f"consecutive_failures >= {self.failure_threshold}"
            self.last_state_change_at = time.monotonic()

    def reset(self) -> None:
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_at = None
        self.open_reason = None
        self.last_state_change_at = time.monotonic()

    def to_dict(self) -> dict[str, object]:
        return {
            "target_id": self.target_id,
            "target_type": self.target_type,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_seconds": self.recovery_timeout_seconds,
            "open_reason": self.open_reason,
        }


class CircuitBreakerManager:
    """Manage circuit breakers for rules and autonomy policies."""

    def __init__(
        self,
        *,
        default_failure_threshold: int = 3,
        default_recovery_timeout_seconds: float = 60.0,
    ) -> None:
        self._breakers: dict[str, CircuitBreakerEntry] = {}
        self._default_failure_threshold = default_failure_threshold
        self._default_recovery_timeout = default_recovery_timeout_seconds

    def get_or_create(
        self,
        target_id: str,
        target_type: str = "rule",
        failure_threshold: int | None = None,
        recovery_timeout_seconds: float | None = None,
    ) -> CircuitBreakerEntry:
        if target_id not in self._breakers:
            self._breakers[target_id] = CircuitBreakerEntry(
                target_id=target_id,
                target_type=target_type,
                failure_threshold=failure_threshold or self._default_failure_threshold,
                recovery_timeout_seconds=recovery_timeout_seconds or self._default_recovery_timeout,
            )
        return self._breakers[target_id]

    def is_open(self, target_id: str) -> bool:
        breaker = self._breakers.get(target_id)
        if breaker is None:
            return False
        return breaker.is_open

    def record_success(self, target_id: str) -> None:
        breaker = self._breakers.get(target_id)
        if breaker is not None:
            breaker.record_success()

    def record_failure(self, target_id: str, reason: str | None = None) -> bool:
        breaker = self._breakers.get(target_id)
        if breaker is None:
            return False
        breaker.record_failure(reason)
        return breaker.state == CircuitState.OPEN

    def reset(self, target_id: str) -> None:
        breaker = self._breakers.get(target_id)
        if breaker is not None:
            breaker.reset()

    def get_state(self, target_id: str) -> dict[str, object] | None:
        breaker = self._breakers.get(target_id)
        if breaker is None:
            return None
        return breaker.to_dict()

    def get_all_states(self) -> dict[str, dict[str, object]]:
        return {tid: b.to_dict() for tid, b in self._breakers.items()}
