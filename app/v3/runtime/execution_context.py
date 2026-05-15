"""Execution context for V3 graph runs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.v3.contracts.agent_message_contracts import AgentMessage
from app.v3.contracts.execution_contracts import (
    ExecutionNode,
    ExecutionReport,
    ExecutionStatus,
    TriggerDiagnostic,
)
from app.v3.contracts.graph_contracts import TaskGraph, TaskNodeStatus


class ExecutionContext(BaseModel):
    """Mutable shared state during graph execution."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    graph_id: str
    shared_state: dict[str, Any] = Field(default_factory=dict)
    node_outputs: dict[str, Any] = Field(default_factory=dict)
    trigger_execution_nodes: list[ExecutionNode] = Field(default_factory=list)
    trigger_diagnostics: list[TriggerDiagnostic] = Field(default_factory=list)
    agent_messages: list[AgentMessage] = Field(default_factory=list)

    def get_output(self, node_id: str, *, default: Any = None) -> Any:
        """Get the output of a completed node by id."""
        return self.node_outputs.get(node_id, default)

    def set_output(self, node_id: str, data: dict[str, Any]) -> None:
        """Store a node's output into both node_outputs and shared_state."""
        self.node_outputs[node_id] = data
        self.shared_state[node_id] = data

    def resolve_input_mapping(
        self,
        input_mapping: dict[str, Any],
        *,
        default_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve an input_mapping dict against shared_state.

        Supports references like ``"node:node_id.output_key"`` or
        ``"shared:key"``.  Unmatched keys are returned as-is.
        """
        resolved: dict[str, Any] = {}
        for key, ref in input_mapping.items():
            if not isinstance(ref, str):
                resolved[key] = ref
                continue

            if ref.startswith("node:"):
                parts = ref.removeprefix("node:").split(".", 1)
                src_node_id = parts[0]
                node_data = self.node_outputs.get(src_node_id)
                if isinstance(node_data, dict) and len(parts) == 2:
                    resolved[key] = node_data.get(parts[1])
                elif len(parts) == 1:
                    resolved[key] = node_data
                else:
                    resolved[key] = None
                continue

            if ref.startswith("shared:"):
                shared_key = ref.removeprefix("shared:")
                resolved[key] = self.shared_state.get(shared_key)
                continue

            resolved[key] = ref

        if default_payload and not input_mapping:
            resolved.update(default_payload)

        return resolved

    def to_report(self, graph: TaskGraph) -> ExecutionReport:
        """Create a serializable execution report."""
        completed = [node.node_id for node in graph.nodes if node.status == TaskNodeStatus.DONE]
        failed = [node.node_id for node in graph.nodes if node.status == TaskNodeStatus.FAILED]
        skipped = [node.node_id for node in graph.nodes if node.status == TaskNodeStatus.SKIPPED]
        recovered = self._collect_recovered_node_ids(failed)
        unresolved_failed = [node_id for node_id in failed if node_id not in recovered]

        if unresolved_failed and not completed and not recovered:
            status = ExecutionStatus.FAILED
        elif unresolved_failed or skipped:
            status = ExecutionStatus.PARTIAL_COMPLETED
        else:
            status = ExecutionStatus.COMPLETED

        graph_execution_nodes = [
            ExecutionNode(
                node_id=node.node_id,
                kind="graph",
                skill_name=node.skill_name,
                status=self._resolve_graph_execution_status(node_id=node.node_id, raw_status=node.status.value, recovered=recovered),
                dependencies=list(node.dependencies),
                summary=str(self.node_outputs.get(node.node_id, {}).get("summary", "")),
                output_data=dict(self.node_outputs.get(node.node_id, {})),
            )
            for node in graph.nodes
        ]

        return ExecutionReport(
            run_id=self.run_id,
            graph_id=self.graph_id,
            status=status,
            completed_node_ids=completed,
            failed_node_ids=unresolved_failed,
            recovered_node_ids=recovered,
            skipped_node_ids=skipped,
            node_outputs=self.node_outputs,
            shared_state=self.shared_state,
            execution_nodes=graph_execution_nodes + list(self.trigger_execution_nodes),
            trigger_diagnostics=list(self.trigger_diagnostics),
            agent_messages=list(self.agent_messages),
        )

    def _collect_recovered_node_ids(self, failed_node_ids: list[str]) -> list[str]:
        if not failed_node_ids:
            return []
        recovered: list[str] = []
        for node_id in failed_node_ids:
            matched = any(
                execution_node.kind == "trigger"
                and execution_node.parent_node_id == node_id
                and execution_node.status == "done"
                and execution_node.recovery_on_success
                for execution_node in self.trigger_execution_nodes
            )
            if matched:
                recovered.append(node_id)
        return recovered

    def _resolve_graph_execution_status(self, *, node_id: str, raw_status: str, recovered: list[str]) -> str:
        if raw_status == TaskNodeStatus.FAILED.value and node_id in recovered:
            return "recovered"
        return raw_status
