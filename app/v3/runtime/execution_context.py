"""Execution context for V3 graph runs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.v3.contracts.execution_contracts import ExecutionReport, ExecutionStatus
from app.v3.contracts.graph_contracts import TaskGraph, TaskNodeStatus


class ExecutionContext(BaseModel):
    """Mutable shared state during graph execution."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    graph_id: str
    shared_state: dict[str, Any] = Field(default_factory=dict)
    node_outputs: dict[str, Any] = Field(default_factory=dict)

    def to_report(self, graph: TaskGraph) -> ExecutionReport:
        """Create a serializable execution report."""
        completed = [node.node_id for node in graph.nodes if node.status == TaskNodeStatus.DONE]
        failed = [node.node_id for node in graph.nodes if node.status == TaskNodeStatus.FAILED]
        skipped = [node.node_id for node in graph.nodes if node.status == TaskNodeStatus.SKIPPED]

        if failed and not completed:
            status = ExecutionStatus.FAILED
        elif failed or skipped:
            status = ExecutionStatus.PARTIAL_COMPLETED
        else:
            status = ExecutionStatus.COMPLETED

        return ExecutionReport(
            run_id=self.run_id,
            graph_id=self.graph_id,
            status=status,
            completed_node_ids=completed,
            failed_node_ids=failed,
            skipped_node_ids=skipped,
            node_outputs=self.node_outputs,
            shared_state=self.shared_state,
        )
