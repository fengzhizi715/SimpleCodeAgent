"""Runtime helpers for V3 task graphs."""

from __future__ import annotations

from app.v3.contracts.graph_contracts import TaskGraph, TaskNode, TaskNodeStatus


class TaskGraphRuntime:
    """Runtime view over a task graph."""

    def __init__(self, graph: TaskGraph) -> None:
        self.graph = graph

    def get_ready_nodes(self, completed: set[str], failed: set[str]) -> list[TaskNode]:
        """Return nodes whose dependencies are satisfied."""
        ready: list[TaskNode] = []

        for node in self.graph.nodes:
            if node.node_id in completed or node.node_id in failed:
                continue
            if node.status in {TaskNodeStatus.RUNNING, TaskNodeStatus.DONE, TaskNodeStatus.FAILED}:
                continue

            failed_dependency = any(dep in failed for dep in node.dependencies)
            if failed_dependency:
                node.status = TaskNodeStatus.SKIPPED
                continue

            deps_done = all(dep in completed for dep in node.dependencies)
            if deps_done:
                ready.append(node)

        return ready
