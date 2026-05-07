"""Graph validation for V3."""

from __future__ import annotations

from app.v3.contracts.graph_contracts import TaskGraph


class GraphValidator:
    """Validate V3 graphs."""

    def validate(self, graph: TaskGraph) -> None:
        """Validate basic graph integrity."""
        node_ids = [node.node_id for node in graph.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Graph contains duplicate node_id values")

        node_id_set = set(node_ids)
        for node in graph.nodes:
            for dep in node.dependencies:
                if dep not in node_id_set:
                    raise ValueError(f"Node {node.node_id} depends on missing node {dep}")
