"""Graph builders for V3."""

from __future__ import annotations

from typing import Any

from app.v3.contracts.graph_contracts import TaskGraph


class GraphBuilder:
    """Convert structured data into V3 graphs."""

    def from_payload(self, payload: dict[str, Any]) -> TaskGraph:
        """Build a graph from a validated dict payload."""
        return TaskGraph.model_validate(payload)
