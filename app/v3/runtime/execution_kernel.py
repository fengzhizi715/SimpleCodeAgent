"""Execution kernel for V3."""

from __future__ import annotations

from typing import Any

from app.v3.contracts.agent_message_contracts import AgentMessage
from app.v3.contracts.event_contracts import EventType, V3Event
from app.v3.contracts.execution_contracts import ExecutionNode, TriggerDiagnostic
from app.v3.contracts.graph_contracts import TaskGraph
from app.v3.events.event_bus import EventBus
from app.v3.events.event_store import EventStore
from app.v3.graph.graph_validator import GraphValidator
from app.v3.governance.execution_budget import ExecutionBudgetState
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
        budget: ExecutionBudgetState | None = None,
    ) -> None:
        self.graph_executor = graph_executor
        self.validator = validator
        self.event_bus = event_bus
        self.event_store = event_store
        self.budget = budget

    async def run_graph(
        self,
        graph: TaskGraph,
        *,
        initial_shared_state: dict[str, Any] | None = None,
        trigger_execution_nodes: list[ExecutionNode] | None = None,
        trigger_diagnostics: list[TriggerDiagnostic] | None = None,
        agent_messages: list[AgentMessage] | None = None,
        skip_validation: bool = False,
    ) -> ExecutionContext:
        """Run a validated graph.

        Args:
            graph: The task graph to execute.
            initial_shared_state: Optional initial shared state dictionary.
            trigger_execution_nodes: Mutable list for trigger-generated execution nodes.
            trigger_diagnostics: Mutable list for trigger diagnostic records.
            agent_messages: Mutable list for agent request/response messages.
            skip_validation: When ``True``, skip graph validation. Use only if
                the caller has already validated the graph.
        """
        if not skip_validation:
            self.validator.validate(graph)
        context = ExecutionContext(
            run_id=graph.run_id,
            graph_id=graph.graph_id,
            shared_state=initial_shared_state or {},
        )
        if trigger_execution_nodes is not None:
            context.trigger_execution_nodes = trigger_execution_nodes
        if trigger_diagnostics is not None:
            context.trigger_diagnostics = trigger_diagnostics
        if agent_messages is not None:
            context.agent_messages = agent_messages

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
        if self.budget is not None and self.budget.events_exhausted:
            return
        if self.event_bus is not None:
            await self.event_bus.publish(event)
