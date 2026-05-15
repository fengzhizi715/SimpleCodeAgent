"""Graph validation for V3."""

from __future__ import annotations

from app.v3.contracts.graph_contracts import TaskGraph
from app.v3.skills.registry import SkillRegistry


class GraphValidator:
    """Validate V3 graphs."""

    def __init__(self, *, skill_registry: SkillRegistry | None = None) -> None:
        self._skill_registry = skill_registry

    def validate(self, graph: TaskGraph) -> None:
        """Validate basic graph integrity."""
        self._validate_structure(graph)
        if self._skill_registry is not None:
            self._validate_skills(graph)

    def _validate_structure(self, graph: TaskGraph) -> None:
        """Validate node uniqueness, dependency existence, and acyclicity."""
        node_ids = [node.node_id for node in graph.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Graph contains duplicate node_id values")

        node_id_set = set(node_ids)
        for node in graph.nodes:
            for dep in node.dependencies:
                if dep not in node_id_set:
                    raise ValueError(f"Node {node.node_id} depends on missing node {dep}")

        adjacency: dict[str, list[str]] = {node.node_id: [] for node in graph.nodes}
        for node in graph.nodes:
            for dep in node.dependencies:
                adjacency[dep].append(node.node_id)

        visiting: set[str] = set()
        visited: set[str] = set()

        def dfs(node_id: str) -> None:
            if node_id in visited:
                return
            if node_id in visiting:
                raise ValueError(f"Graph contains a cycle involving node {node_id}")
            visiting.add(node_id)
            for child_id in adjacency[node_id]:
                dfs(child_id)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in adjacency:
            dfs(node_id)

    def _validate_skills(self, graph: TaskGraph) -> None:
        """Validate that every node references a registered, enabled skill."""
        for node in graph.nodes:
            try:
                self._skill_registry.get(node.skill_name)
            except ValueError as exc:
                raise ValueError(
                    f"Node {node.node_id} references an invalid skill '{node.skill_name}': {exc}"
                ) from exc
