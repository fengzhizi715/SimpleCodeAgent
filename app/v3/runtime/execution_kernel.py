"""Execution kernel for V3."""

from __future__ import annotations

from app.v3.contracts.event_contracts import EventType, V3Event
from app.v3.contracts.graph_contracts import TaskGraph
from app.v3.events.event_bus import EventBus
from app.v3.events.event_store import EventStore
from app.v3.graph.graph_validator import GraphValidator
from app.v3.runtime.execution_context import ExecutionContext
from app.v3.runtime.graph_executor import GraphExecutor


class ExecutionKernel:
    """Validate and run V3 task graphs."""

    def __init__(
        self,
        graph_executor: GraphExecutor,
        validator: GraphValidator,
        *,
        event_bus: EventBus | None = None,
        event_store: EventStore | None = None,
    ) -> None:
        self.graph_executor = graph_executor
        self.validator = validator
        self.event_bus = event_bus
        self.event_store = event_store

    async def run_graph(self, graph: TaskGraph) -> ExecutionContext:
        """Run a validated graph."""
        self.validator.validate(graph)
        context = ExecutionContext(run_id=graph.run_id, graph_id=graph.graph_id)

        await self._publish(
            V3Event(
                run_id=graph.run_id,
                event_type=EventType.GRAPH_STARTED.value,
                source="execution_kernel",
                payload={"graph_id": graph.graph_id, "node_count": len(graph.nodes)},
            )
        )
        result = await self.graph_executor.execute_graph(graph, context)
        await self._publish(
            V3Event(
                run_id=graph.run_id,
                event_type=EventType.GRAPH_FINISHED.value,
                source="execution_kernel",
                payload=result.to_report(graph).model_dump(mode="json"),
            )
        )
        return result

    async def _publish(self, event: V3Event) -> None:
        if self.event_store is not None:
            self.event_store.append(event)
        if self.event_bus is not None:
            await self.event_bus.publish(event)
