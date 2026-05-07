"""Local async event bus for V3."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable

from app.v3.contracts.event_contracts import V3Event

EventHandler = Callable[[V3Event], Awaitable[None]]


class EventBus:
    """In-process pub/sub bus."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe a handler to an event type."""
        self._handlers[event_type].append(handler)

    async def publish(self, event: V3Event) -> None:
        """Publish an event to all subscribers."""
        for handler in self._handlers.get(event.event_type, []):
            await handler(event)
