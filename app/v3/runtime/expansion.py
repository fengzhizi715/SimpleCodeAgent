"""Dynamic expansion for V3.2 Phase 2.

Supports limited, auditable execution expansion:
- Append virtual execution nodes at graph periphery
- Instantiate subgraph templates
- Append execution plan

Does NOT allow:
- Arbitrary insertion of nodes during execution
- Automatic reordering of entire graph
- Complex graph optimization
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.v3.contracts.expansion_contracts import (
    ExpansionRequest,
    ExpansionResult,
    ExpansionStatus,
    ExpansionType,
    SubgraphTemplate,
)
from app.v3.contracts.graph_contracts import TaskGraph, TaskNode, TaskNodeStatus


class DynamicExpansion:
    """Controlled dynamic expansion of execution plans.

    Only allows:
    - Appending virtual nodes at graph periphery
    - Instantiating subgraph templates
    - Appending execution plan entries

    Does NOT mutate the original validated graph.
    """

    def __init__(self, run_id: str, original_graph: TaskGraph) -> None:
        self.run_id = run_id
        self.original_graph = original_graph
        self._requests: list[ExpansionRequest] = []
        self._appended_nodes: list[TaskNode] = []
        self._templates: dict[str, SubgraphTemplate] = {}

    @property
    def requests(self) -> list[ExpansionRequest]:
        return list(self._requests)

    @property
    def appended_nodes(self) -> list[TaskNode]:
        return list(self._appended_nodes)

    def register_template(self, template: SubgraphTemplate) -> None:
        self._templates[template.template_id] = template

    def request_append_virtual_node(
        self,
        *,
        node: TaskNode,
        reason: str,
        source_node_id: str | None = None,
        source_event_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExpansionRequest:
        request = ExpansionRequest(
            run_id=self.run_id,
            expansion_type=ExpansionType.APPEND_VIRTUAL_NODE,
            reason=reason,
            source_node_id=source_node_id,
            source_event_id=source_event_id,
            virtual_node=node,
            metadata=metadata or {},
        )
        self._requests.append(request)
        return request

    def request_instantiate_subgraph(
        self,
        *,
        template_id: str | None = None,
        template_data: SubgraphTemplate | None = None,
        reason: str,
        source_node_id: str | None = None,
        source_event_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExpansionRequest:
        request = ExpansionRequest(
            run_id=self.run_id,
            expansion_type=ExpansionType.INSTANTIATE_SUBGRAPH,
            reason=reason,
            source_node_id=source_node_id,
            source_event_id=source_event_id,
            subgraph_template_id=template_id,
            subgraph_template_data=template_data,
            metadata=metadata or {},
        )
        self._requests.append(request)
        return request

    def request_append_execution_plan(
        self,
        *,
        plan: list[dict[str, Any]],
        reason: str,
        source_node_id: str | None = None,
        source_event_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExpansionRequest:
        request = ExpansionRequest(
            run_id=self.run_id,
            expansion_type=ExpansionType.APPEND_EXECUTION_PLAN,
            reason=reason,
            source_node_id=source_node_id,
            source_event_id=source_event_id,
            execution_plan=plan,
            metadata=metadata or {},
        )
        self._requests.append(request)
        return request

    def approve(self, request_id: str) -> ExpansionResult:
        request = self._find_request(request_id)
        if request is None:
            return ExpansionResult(
                request_id=request_id,
                run_id=self.run_id,
                success=False,
                error="Request not found",
            )

        if request.status != ExpansionStatus.PENDING:
            return ExpansionResult(
                request_id=request_id,
                run_id=self.run_id,
                success=False,
                error=f"Request already {request.status.value}",
            )

        result = self._apply_expansion(request)
        request.status = ExpansionStatus.APPLIED if result.success else ExpansionStatus.FAILED
        request.applied_at = datetime.now(UTC)
        return result

    def reject(self, request_id: str, reason: str) -> ExpansionRequest | None:
        request = self._find_request(request_id)
        if request is None:
            return None
        if request.status != ExpansionStatus.PENDING:
            return None
        request.status = ExpansionStatus.REJECTED
        request.rejection_reason = reason
        return request

    def get_expanded_graph(self) -> TaskGraph:
        """Return a view of the graph including appended nodes.

        Does NOT mutate the original graph.
        """
        if not self._appended_nodes:
            return self.original_graph

        combined_nodes = list(self.original_graph.nodes) + self._appended_nodes
        return TaskGraph(
            graph_id=f"{self.original_graph.graph_id}+expanded",
            run_id=self.original_graph.run_id,
            nodes=combined_nodes,
        )

    def _apply_expansion(self, request: ExpansionRequest) -> ExpansionResult:
        if request.expansion_type == ExpansionType.APPEND_VIRTUAL_NODE:
            return self._apply_virtual_node(request)
        if request.expansion_type == ExpansionType.INSTANTIATE_SUBGRAPH:
            return self._apply_subgraph(request)
        if request.expansion_type == ExpansionType.APPEND_EXECUTION_PLAN:
            return self._apply_execution_plan(request)
        return ExpansionResult(
            request_id=request.request_id,
            run_id=self.run_id,
            success=False,
            error=f"Unknown expansion type: {request.expansion_type}",
        )

    def _apply_virtual_node(self, request: ExpansionRequest) -> ExpansionResult:
        if request.virtual_node is None:
            return ExpansionResult(
                request_id=request.request_id,
                run_id=self.run_id,
                success=False,
                error="No virtual node provided",
            )

        node = request.virtual_node.model_copy(
            update={
                "node_id": f"expanded:{request.request_id}",
                "status": TaskNodeStatus.PENDING,
            }
        )
        self._appended_nodes.append(node)
        return ExpansionResult(
            request_id=request.request_id,
            run_id=self.run_id,
            success=True,
            appended_nodes=[node],
            metadata={"expansion_type": "virtual_node"},
        )

    def _apply_subgraph(self, request: ExpansionRequest) -> ExpansionResult:
        template = None
        if request.subgraph_template_id is not None:
            template = self._templates.get(request.subgraph_template_id)
        elif request.subgraph_template_data is not None:
            template = request.subgraph_template_data

        if template is None:
            return ExpansionResult(
                request_id=request.request_id,
                run_id=self.run_id,
                success=False,
                error="Subgraph template not found",
            )

        prefix = f"expanded:{request.request_id}"
        instantiated: list[TaskNode] = []
        for original_node in template.nodes:
            new_node = original_node.model_copy(
                update={
                    "node_id": f"{prefix}:{original_node.node_id}",
                    "status": TaskNodeStatus.PENDING,
                    "dependencies": [
                        f"{prefix}:{dep}" for dep in original_node.dependencies
                    ],
                }
            )
            instantiated.append(new_node)

        self._appended_nodes.extend(instantiated)
        return ExpansionResult(
            request_id=request.request_id,
            run_id=self.run_id,
            success=True,
            appended_nodes=instantiated,
            metadata={"expansion_type": "subgraph", "template_id": template.template_id},
        )

    def _apply_execution_plan(self, request: ExpansionRequest) -> ExpansionResult:
        nodes: list[TaskNode] = []
        for i, plan_entry in enumerate(request.execution_plan):
            node = TaskNode(
                node_id=f"expanded:{request.request_id}:plan_{i}",
                skill_name=plan_entry.get("skill_name", "unknown"),
                dependencies=list(plan_entry.get("dependencies", [])),
                input_payload=dict(
                    plan_entry.get(
                        "input_payload",
                        plan_entry.get("input_mapping", {}),
                    )
                ),
                status=TaskNodeStatus.PENDING,
            )
            nodes.append(node)

        self._appended_nodes.extend(nodes)
        return ExpansionResult(
            request_id=request.request_id,
            run_id=self.run_id,
            success=True,
            appended_nodes=nodes,
            metadata={"expansion_type": "execution_plan", "plan_count": len(nodes)},
        )

    def _find_request(self, request_id: str) -> ExpansionRequest | None:
        for req in self._requests:
            if req.request_id == request_id:
                return req
        return None
