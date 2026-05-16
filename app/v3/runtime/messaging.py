"""Runtime messaging for V3.2 Phase 2.

Provides queued, delayed, and policy-governed message passing.
Not a free-form agent chat system. Controlled execution messaging only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.v3.contracts.agent_message_contracts import AgentMessage, AgentMessageType
from app.v3.contracts.messaging_contracts import MessagePolicy, MessageStatus, RuntimeMessage


class RuntimeMessaging:
    """Controlled runtime messaging system.

    Supports:
    - Queued messages
    - Delayed messages
    - Message policy enforcement
    - Allowed targets
    - Max rounds
    - Message type whitelist

    This is NOT a free-form agent chat system.
    """

    def __init__(self, run_id: str, policy: MessagePolicy | None = None) -> None:
        self.run_id = run_id
        self.policy = policy or MessagePolicy()
        self._messages: list[RuntimeMessage] = []
        self._round_count: dict[str, int] = {}

    @property
    def messages(self) -> list[RuntimeMessage]:
        return list(self._messages)

    def get_message(self, message_id: str) -> RuntimeMessage | None:
        for msg in self._messages:
            if msg.message_id == message_id:
                return msg
        return None

    def list_messages_by_status(self, status: MessageStatus) -> list[RuntimeMessage]:
        return [m for m in self._messages if m.status == status]

    def list_messages_by_actor(self, actor: str) -> list[RuntimeMessage]:
        return [
            m for m in self._messages
            if m.from_actor == actor or m.to_actor == actor
        ]

    def list_due_messages(self) -> list[RuntimeMessage]:
        return [
            m for m in self._messages
            if m.status in (MessageStatus.QUEUED, MessageStatus.DELAYED)
            and m.is_due
        ]

    def send(
        self,
        *,
        from_actor: str,
        to_actor: str,
        message_type: str,
        payload: dict[str, Any] | None = None,
        delay_seconds: float | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[RuntimeMessage | None, str | None]:
        """Send a message. Returns (message, rejection_reason)."""
        rejection = self._validate_message(
            from_actor=from_actor,
            to_actor=to_actor,
            message_type=message_type,
        )
        if rejection is not None:
            msg = RuntimeMessage(
                run_id=self.run_id,
                from_actor=from_actor,
                to_actor=to_actor,
                message_type=message_type,
                payload=payload or {},
                status=MessageStatus.REJECTED,
                rejected_reason=rejection,
                correlation_id=correlation_id,
                metadata=metadata or {},
            )
            self._messages.append(msg)
            return None, rejection

        round_number = self._get_round_count(to_actor) + 1
        if round_number > self.policy.max_rounds:
            msg = RuntimeMessage(
                run_id=self.run_id,
                from_actor=from_actor,
                to_actor=to_actor,
                message_type=message_type,
                payload=payload or {},
                status=MessageStatus.REJECTED,
                round_number=round_number,
                rejected_reason=f"max_rounds exceeded: {round_number} > {self.policy.max_rounds}",
                correlation_id=correlation_id,
                metadata=metadata or {},
            )
            self._messages.append(msg)
            return None, msg.rejected_reason

        status = MessageStatus.QUEUED
        deliver_at: datetime | None = None
        if delay_seconds is not None and delay_seconds > 0:
            if delay_seconds > self.policy.max_delay_seconds:
                msg = RuntimeMessage(
                    run_id=self.run_id,
                    from_actor=from_actor,
                    to_actor=to_actor,
                    message_type=message_type,
                    payload=payload or {},
                    status=MessageStatus.REJECTED,
                    rejected_reason=f"delay exceeds max: {delay_seconds} > {self.policy.max_delay_seconds}",
                    correlation_id=correlation_id,
                    metadata=metadata or {},
                )
                self._messages.append(msg)
                return None, msg.rejected_reason
            status = MessageStatus.DELAYED
            deliver_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)

        msg = RuntimeMessage(
            run_id=self.run_id,
            from_actor=from_actor,
            to_actor=to_actor,
            message_type=message_type,
            payload=payload or {},
            status=status,
            round_number=round_number,
            correlation_id=correlation_id,
            deliver_at=deliver_at,
            metadata=metadata or {},
        )
        self._messages.append(msg)
        self._round_count[to_actor] = round_number
        return msg, None

    def deliver(self, message_id: str) -> RuntimeMessage | None:
        msg = self.get_message(message_id)
        if msg is None:
            return None
        if msg.status not in (MessageStatus.QUEUED, MessageStatus.DELAYED):
            return None
        if not msg.is_due:
            return None

        msg.status = MessageStatus.DELIVERED
        msg.delivered_at = datetime.now(UTC)
        return msg

    def tick(self) -> list[RuntimeMessage]:
        """Process delayed messages that are now due. Returns delivered messages."""
        delivered: list[RuntimeMessage] = []
        for msg in self.list_due_messages():
            result = self.deliver(msg.message_id)
            if result is not None:
                delivered.append(result)
        return delivered

    def to_agent_messages(self) -> list[AgentMessage]:
        """Convert delivered messages to AgentMessage format."""
        result: list[AgentMessage] = []
        for msg in self._messages:
            if msg.status == MessageStatus.DELIVERED:
                result.append(
                    AgentMessage(
                        run_id=self.run_id,
                        from_actor=msg.from_actor,
                        to_actor=msg.to_actor,
                        message_type=AgentMessageType.REQUEST,
                        payload=msg.payload,
                        correlation_id=msg.correlation_id,
                    )
                )
        return result

    def _validate_message(
        self,
        *,
        from_actor: str,
        to_actor: str,
        message_type: str,
    ) -> str | None:
        if not self.policy.allow_self_message and from_actor == to_actor:
            return "self_message_not_allowed"

        if self.policy.allowed_targets is not None:
            if to_actor not in self.policy.allowed_targets:
                return f"target_not_allowed: {to_actor}"

        if self.policy.message_type_whitelist is not None:
            if message_type not in self.policy.message_type_whitelist:
                return f"message_type_not_allowed: {message_type}"

        return None

    def _get_round_count(self, actor: str) -> int:
        return self._round_count.get(actor, 0)
