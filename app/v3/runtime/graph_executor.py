"""Graph executor for V3."""

from __future__ import annotations

import asyncio

from app.v3.contracts.event_contracts import EventType, V3Event
from app.v3.contracts.graph_contracts import TaskGraph, TaskNodeStatus
from app.v3.contracts.skill_contracts import SkillInput
from app.v3.events.event_bus import EventBus
from app.v3.events.event_store import EventStore
from app.v3.graph.task_graph import TaskGraphRuntime
from app.v3.runtime.execution_context import ExecutionContext
from app.v3.runtime.skill_executor import SkillExecutor


class GraphExecutor:
    """Execute a graph with simple wave-based parallelism for ready nodes."""

    def __init__(
        self,
        skill_executor: SkillExecutor,
        *,
        event_bus: EventBus | None = None,
        event_store: EventStore | None = None,
    ) -> None:
        self.skill_executor = skill_executor
        self.event_bus = event_bus
        self.event_store = event_store

    async def execute_graph(self, graph: TaskGraph, context: ExecutionContext) -> ExecutionContext:
        """Execute all ready graph nodes until convergence."""
        runtime = TaskGraphRuntime(graph)
        completed: set[str] = set()
        failed: set[str] = set()

        while len(completed) + len(failed) < len(graph.nodes):
            ready_nodes = runtime.get_ready_nodes(completed, failed)
            if not ready_nodes:
                break

            context_snapshot = dict(context.shared_state)
            for node in ready_nodes:
                node.status = TaskNodeStatus.RUNNING
                await self._publish(
                    V3Event(
                        run_id=context.run_id,
                        event_type=EventType.SKILL_STARTED.value,
                        source=node.skill_name,
                        payload={"node_id": node.node_id, "input_payload": node.input_payload},
                    )
                )

            outputs = await asyncio.gather(
                *[
                    self.skill_executor.execute(
                        node.skill_name,
                        SkillInput(
                            run_id=context.run_id,
                            payload=node.input_payload,
                            context={
                                **context_snapshot,
                                "current_node_id": node.node_id,
                            },
                        ),
                    )
                    for node in ready_nodes
                ]
            )

            for node, output in zip(ready_nodes, outputs, strict=True):
                if output.success:
                    node.status = TaskNodeStatus.DONE
                    completed.add(node.node_id)
                    context.node_outputs[node.node_id] = output.data
                    context.shared_state[node.node_id] = output.data
                    await self._publish(
                        V3Event(
                            run_id=context.run_id,
                            event_type=EventType.SKILL_FINISHED.value,
                            source=node.skill_name,
                            payload={
                                "node_id": node.node_id,
                                "summary": output.summary,
                                "data": output.data,
                            },
                        )
                    )
                    domain_event = self._build_domain_event_on_success(
                        node_id=node.node_id,
                        skill_name=node.skill_name,
                        run_id=context.run_id,
                        output=output.data,
                    )
                    if domain_event is not None:
                        await self._publish(domain_event)
                    continue

                node.status = TaskNodeStatus.FAILED
                failed.add(node.node_id)
                context.node_outputs[node.node_id] = {
                    "error": output.error,
                    "summary": output.summary,
                }
                await self._publish(
                    V3Event(
                        run_id=context.run_id,
                        event_type=EventType.SKILL_FAILED.value,
                        source=node.skill_name,
                        payload={
                            "node_id": node.node_id,
                            "summary": output.summary,
                            "error": output.error,
                        },
                    )
                )
                domain_event = self._build_domain_event_on_failure(
                    node_id=node.node_id,
                    skill_name=node.skill_name,
                    run_id=context.run_id,
                    error=output.error,
                    summary=output.summary,
                    data=output.data,
                )
                if domain_event is not None:
                    await self._publish(domain_event)

        return context

    async def _publish(self, event: V3Event) -> None:
        if self.event_store is not None:
            self.event_store.append(event)
        if self.event_bus is not None:
            await self.event_bus.publish(event)

    def _build_domain_event_on_success(
        self,
        *,
        node_id: str,
        skill_name: str,
        run_id: str,
        output: dict[str, object],
    ) -> V3Event | None:
        if skill_name != "coding":
            return None
        return V3Event(
            run_id=run_id,
            event_type=EventType.CODE_UPDATED.value,
            source=skill_name,
            payload={
                "node_id": node_id,
                "changed_files": output.get("changed_files", []),
                "patch_summary": output.get("patch_summary", ""),
            },
        )

    def _build_domain_event_on_failure(
        self,
        *,
        node_id: str,
        skill_name: str,
        run_id: str,
        error: str | None,
        summary: str,
        data: dict[str, object],
    ) -> V3Event | None:
        if skill_name != "test_runner":
            return None
        return V3Event(
            run_id=run_id,
            event_type=EventType.TEST_FAILED.value,
            source=skill_name,
            payload={
                "node_id": node_id,
                "error": error,
                "summary": summary,
                "failure_type": data.get("failure_type"),
                "executed_command": data.get("executed_command"),
            },
        )
