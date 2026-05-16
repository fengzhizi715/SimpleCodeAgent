"""Graph executor for V3."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.v3.contracts.agent_message_contracts import AgentMessage, AgentMessageType
from app.v3.contracts.audit_contracts import StopReason
from app.v3.contracts.event_contracts import EventType, V3Event
from app.v3.contracts.graph_contracts import TaskGraph, TaskNodeStatus
from app.v3.contracts.skill_contracts import SkillInput
from app.v3.events.event_bus import EventBus
from app.v3.events.event_store import EventStore
from app.v3.governance.execution_budget import ExecutionBudgetState
from app.v3.graph.task_graph import TaskGraphRuntime
from app.v3.runtime.execution_context import ExecutionContext
from app.v3.runtime.skill_executor import SkillExecutor

if TYPE_CHECKING:
    from app.v3.audit.audit_store import AuditLogStore


class GraphExecutor:
    """Execute a graph with simple wave-based parallelism for ready nodes."""

    def __init__(
        self,
        skill_executor: SkillExecutor,
        *,
        event_bus: EventBus | None = None,
        event_store: EventStore | None = None,
        budget: ExecutionBudgetState | None = None,
        audit_store: AuditLogStore | None = None,
    ) -> None:
        self.skill_executor = skill_executor
        self.event_bus = event_bus
        self.event_store = event_store
        self.budget = budget
        self.audit_store = audit_store

    async def execute_graph(self, graph: TaskGraph, context: ExecutionContext) -> ExecutionContext:
        """Execute all ready graph nodes until convergence."""
        runtime = TaskGraphRuntime(graph)
        completed: set[str] = set()
        failed: set[str] = set()
        skipped_recorded: set[str] = set()

        while len(completed) + len(failed) < len(graph.nodes):
            if self._should_stop_for_budget():
                self._mark_pending_nodes_as_skipped(
                    graph=graph,
                    context=context,
                    reason=self._budget_stop_reason(),
                )
                break
            ready_nodes = runtime.get_ready_nodes(completed, failed)
            await self._record_newly_skipped_nodes(
                graph=graph,
                context=context,
                failed=failed,
                skipped_recorded=skipped_recorded,
            )
            if not ready_nodes:
                break

            context_snapshot = dict(context.shared_state)
            request_message_ids: dict[str, str] = {}

            wave_nodes: list[TaskNode] = []
            for node in ready_nodes:
                if self.budget is not None and not self.budget.consume_step():
                    for wn in wave_nodes:
                        wn.status = TaskNodeStatus.SKIPPED
                        context.node_outputs[wn.node_id] = {
                            "summary": "Skipped because execution budget was exhausted",
                            "skip_reason": "execution_budget_exhausted",
                            "details": self._budget_stop_reason(),
                        }
                    self._mark_pending_nodes_as_skipped(
                        graph=graph,
                        context=context,
                        reason=self._budget_stop_reason(),
                    )
                    return context
                wave_nodes.append(node)

            for node in wave_nodes:
                node.status = TaskNodeStatus.RUNNING
                request_message = AgentMessage(
                    run_id=context.run_id,
                    from_actor="graph_executor",
                    to_actor=node.skill_name,
                    message_type=AgentMessageType.REQUEST,
                    node_id=node.node_id,
                    payload={"input_payload": node.input_payload},
                )
                context.agent_messages.append(request_message)
                request_message_ids[node.node_id] = request_message.message_id
                await self._publish(
                    V3Event(
                        run_id=context.run_id,
                        event_type=EventType.SKILL_STARTED.value,
                        source=node.skill_name,
                        correlation_id=request_message.message_id,
                        execution_chain_id=self._build_execution_chain_id(
                            run_id=context.run_id,
                            node_id=node.node_id,
                            skill_name=node.skill_name,
                        ),
                        payload={"node_id": node.node_id, "input_payload": node.input_payload},
                    )
                )
                test_started_event = self._build_domain_event_on_start(
                    node_id=node.node_id,
                    skill_name=node.skill_name,
                    run_id=context.run_id,
                    input_payload=node.input_payload,
                )
                if test_started_event is not None:
                    await self._publish(test_started_event)

            async def _execute_node(node):
                try:
                    output = await self.skill_executor.execute(
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
                    return node, output, None
                except BaseException as exc:  # pragma: no cover - defensive guard
                    return node, None, exc

            tasks = [asyncio.create_task(_execute_node(node)) for node in ready_nodes]

            for finished_task in asyncio.as_completed(tasks):
                node, output, exc = await finished_task
                if exc is not None:
                    output = self.skill_executor.create_error_output(
                        error=str(exc),
                        summary=f"Node {node.node_id} raised unexpected exception: {exc!r}",
                    )
                if output.success:
                    node.status = TaskNodeStatus.DONE
                    completed.add(node.node_id)
                    context.set_output(node.node_id, output.data)
                    context.agent_messages.append(
                        AgentMessage(
                            run_id=context.run_id,
                            from_actor=node.skill_name,
                            to_actor="graph_executor",
                            message_type=AgentMessageType.RESPONSE,
                            node_id=node.node_id,
                            correlation_id=request_message_ids.get(node.node_id),
                            payload={
                                "success": True,
                                "summary": output.summary,
                                "data": output.data,
                            },
                        )
                    )
                    await self._publish(
                        V3Event(
                            run_id=context.run_id,
                            event_type=EventType.SKILL_FINISHED.value,
                            source=node.skill_name,
                            correlation_id=request_message_ids.get(node.node_id),
                            execution_chain_id=self._build_execution_chain_id(
                                run_id=context.run_id,
                                node_id=node.node_id,
                                skill_name=node.skill_name,
                            ),
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
                context.agent_messages.append(
                    AgentMessage(
                        run_id=context.run_id,
                        from_actor=node.skill_name,
                        to_actor="graph_executor",
                        message_type=AgentMessageType.RESPONSE,
                        node_id=node.node_id,
                        correlation_id=request_message_ids.get(node.node_id),
                        payload={
                            "success": False,
                            "summary": output.summary,
                            "error": output.error,
                            "data": output.data,
                        },
                    )
                )
                await self._publish(
                    V3Event(
                        run_id=context.run_id,
                        event_type=EventType.SKILL_FAILED.value,
                        source=node.skill_name,
                        correlation_id=request_message_ids.get(node.node_id),
                        execution_chain_id=self._build_execution_chain_id(
                            run_id=context.run_id,
                            node_id=node.node_id,
                            skill_name=node.skill_name,
                        ),
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

    async def _record_newly_skipped_nodes(
        self,
        *,
        graph: TaskGraph,
        context: ExecutionContext,
        failed: set[str],
        skipped_recorded: set[str],
    ) -> None:
        for node in graph.nodes:
            if node.status != TaskNodeStatus.SKIPPED or node.node_id in skipped_recorded:
                continue
            failed_dependencies = [dep for dep in node.dependencies if dep in failed]
            payload = {
                "summary": "Skipped because one or more dependencies failed",
                "skip_reason": "dependency_failed",
                "failed_dependencies": failed_dependencies,
            }
            context.node_outputs[node.node_id] = payload
            context.agent_messages.append(
                AgentMessage(
                    run_id=context.run_id,
                    from_actor="graph_executor",
                    to_actor=node.skill_name,
                    message_type=AgentMessageType.RESPONSE,
                    node_id=node.node_id,
                    payload={
                        "success": False,
                        "skipped": True,
                        **payload,
                    },
                )
            )
            skipped_recorded.add(node.node_id)
            await self._publish(
                V3Event(
                    run_id=context.run_id,
                    event_type=EventType.SKILL_SKIPPED.value,
                    source=node.skill_name,
                    execution_chain_id=self._build_execution_chain_id(
                        run_id=context.run_id,
                        node_id=node.node_id,
                        skill_name=node.skill_name,
                    ),
                    payload={
                        "node_id": node.node_id,
                        **payload,
                    },
                )
            )

    async def _publish(self, event: V3Event) -> None:
        if self.event_store is not None:
            self.event_store.append(event)
        if self.budget is not None and self.budget.events_exhausted:
            return
        if self.event_bus is not None:
            await self.event_bus.publish(event)

    def _should_stop_for_budget(self) -> bool:
        if self.budget is None:
            return False
        return (
            self.budget.runtime_exhausted
            or self.budget.steps_exhausted
            or self.budget.events_exhausted
        )

    def _budget_stop_reason(self) -> str:
        if self.budget is None:
            return "budget_not_available"
        reasons = self.budget.get_exhaustion_reasons()
        return "; ".join(reasons) if reasons else "budget_exhausted"

    def _mark_pending_nodes_as_skipped(
        self,
        *,
        graph: TaskGraph,
        context: ExecutionContext,
        reason: str,
    ) -> None:
        for node in graph.nodes:
            if node.status != TaskNodeStatus.PENDING:
                continue
            node.status = TaskNodeStatus.SKIPPED
            context.node_outputs[node.node_id] = {
                "summary": "Skipped because execution budget was exhausted",
                "skip_reason": "execution_budget_exhausted",
                "details": reason,
            }
        stop_reason = StopReason(
            run_id=context.run_id,
            reason_type="budget_exhausted",
            actor="graph_executor",
            summary=f"Execution budget exhausted: {reason}",
            details={"message": reason},
        )
        if self.audit_store is not None:
            self.audit_store.add_stop_reason(stop_reason)
        stop_reasons: list[dict[str, object]] = context.shared_state.get("__stop_reasons__", [])
        stop_reasons.append(stop_reason.model_dump())
        context.shared_state["__stop_reasons__"] = stop_reasons

    def _build_domain_event_on_success(
        self,
        *,
        node_id: str,
        skill_name: str,
        run_id: str,
        output: dict[str, object],
    ) -> V3Event | None:
        if skill_name == "test_runner":
            return V3Event(
                run_id=run_id,
                event_type=EventType.TEST_PASSED.value,
                source=skill_name,
                execution_chain_id=self._build_execution_chain_id(
                    run_id=run_id,
                    node_id=node_id,
                    skill_name=skill_name,
                ),
                payload={
                    "node_id": node_id,
                    "executed_command": output.get("executed_command"),
                    "summary": f"Tests passed: {output.get('executed_command') or 'pytest -q'}",
                },
            )
        if skill_name != "coding":
            return None
        return V3Event(
            run_id=run_id,
            event_type=EventType.CODE_UPDATED.value,
            source=skill_name,
            execution_chain_id=self._build_execution_chain_id(
                run_id=run_id,
                node_id=node_id,
                skill_name=skill_name,
            ),
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
            execution_chain_id=self._build_execution_chain_id(
                run_id=run_id,
                node_id=node_id,
                skill_name=skill_name,
            ),
            payload={
                "node_id": node_id,
                "error": error,
                "summary": summary,
                "failure_type": data.get("failure_type"),
                "executed_command": data.get("executed_command"),
            },
        )

    def _build_domain_event_on_start(
        self,
        *,
        node_id: str,
        skill_name: str,
        run_id: str,
        input_payload: dict[str, object],
    ) -> V3Event | None:
        if skill_name != "test_runner":
            return None
        return V3Event(
            run_id=run_id,
            event_type=EventType.TEST_STARTED.value,
            source=skill_name,
            execution_chain_id=self._build_execution_chain_id(
                run_id=run_id,
                node_id=node_id,
                skill_name=skill_name,
            ),
            payload={
                "node_id": node_id,
                "executed_command": input_payload.get("command") or input_payload.get("test_command") or "pytest -q",
            },
        )

    @staticmethod
    def _build_execution_chain_id(*, run_id: str, node_id: str, skill_name: str) -> str:
        return f"{run_id}:{node_id}:{skill_name}"
