"""Shared V3 run helpers used by API and CLI entrypoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from app.db.sqlite import SQLiteDB
from app.contracts.trace import TraceEvent
from app.trace.recorder import JsonlTraceRecorder
from app.trace.repository import SQLiteTraceRepository
from app.v3 import build_default_skill_registry
from app.v3.contracts.execution_contracts import ExecutionNode, ExecutionReport, TriggerDiagnostic
from app.v3.contracts.graph_contracts import GraphInspection, TaskGraph
from app.v3.contracts.planning_contracts import PlanningResult
from app.v3.contracts.skill_contracts import SkillInput
from app.v3.contracts.trigger_contracts import TriggerRule
from app.v3.events.event_bus import EventBus
from app.v3.events.event_store import EventStore
from app.v3.graph.graph_builder import GraphBuilder
from app.v3.graph.graph_validator import GraphValidator
from app.v3.runtime.execution_kernel import ExecutionKernel
from app.v3.runtime.graph_executor import GraphExecutor
from app.v3.runtime.skill_executor import SkillExecutor
from app.v3.trace import attach_trace_collector
from app.v3.trigger.trigger_engine import TriggerEngine
from app.v3.trigger.trigger_registry import TriggerRegistry
from app.v3.skills.registry import SkillRegistry


async def run_v3(
    *,
    goal: str | None = None,
    graph: TaskGraph | None = None,
    workdir: str | None = None,
    rag_id: str | None = None,
    rag_ids: list[str] | None = None,
    coding_execution_mode: str = "internal",
    external_coding: dict[str, object] | None = None,
    include_events: bool = True,
    include_trace: bool = True,
    registry: SkillRegistry | None = None,
    trigger_rules: list[TriggerRule] | None = None,
    plan_only: bool = False,
) -> dict[str, Any]:
    """Run a V3 goal or graph and return serializable output."""
    resolved_workdir = str(Path(workdir or ".").expanduser().resolve())
    event_bus = EventBus()
    event_store = EventStore()
    trace_events = attach_trace_collector(event_bus)
    trigger_execution_nodes: list[ExecutionNode] = []
    trigger_diagnostics: list[TriggerDiagnostic] = []
    skill_registry = registry or build_default_skill_registry(workspace_root=resolved_workdir)
    skill_executor = SkillExecutor(skill_registry)
    graph_executor = GraphExecutor(skill_executor, event_bus=event_bus, event_store=event_store)
    kernel = ExecutionKernel(
        graph_executor=graph_executor,
        validator=GraphValidator(),
        event_bus=event_bus,
        event_store=event_store,
    )

    resolved_graph = graph
    planned_trigger_rules: list[TriggerRule] = []
    planning_result: PlanningResult | None = None
    inspection: GraphInspection | None = None
    if resolved_graph is None:
        if not (goal or "").strip():
            raise ValueError("必须提供 graph 或 goal。")
        planning_result = await plan_v3_graph(
            goal=goal or "",
            workdir=resolved_workdir,
            skill_executor=skill_executor,
            rag_id=rag_id,
            rag_ids=rag_ids,
            coding_execution_mode=coding_execution_mode,
            external_coding=external_coding,
        )
        resolved_graph = planning_result.graph
        planned_trigger_rules = list(planning_result.trigger_rules)

    if resolved_graph is None:
        raise ValueError("未能解析可执行的 graph。")
    if planning_result is not None:
        inspection = build_graph_inspection(planning_result.graph)
    elif graph is not None:
        inspection = build_graph_inspection(graph)

    if plan_only:
        return {
            "report": None,
            "planning": planning_result,
            "inspection": inspection,
            "events": [],
            "trace": [],
        }

    effective_trigger_rules = list(trigger_rules or planned_trigger_rules)
    _attach_trigger_engine(
        event_bus=event_bus,
        event_store=event_store,
        execution_nodes=trigger_execution_nodes,
        diagnostics=trigger_diagnostics,
        trigger_rules=effective_trigger_rules,
        skill_executor=skill_executor,
    )

    context = await kernel.run_graph(
        resolved_graph,
        initial_shared_state={
            "workspace_root": resolved_workdir,
            "planning": (
                {
                    **planning_result.model_dump(mode="json", exclude={"graph", "trigger_rules"}),
                    "execution_layers": inspection.execution_layers if inspection is not None else [],
                }
                if planning_result is not None
                else {}
            ),
        },
        trigger_execution_nodes=trigger_execution_nodes,
        trigger_diagnostics=trigger_diagnostics,
    )
    report = context.to_report(resolved_graph)
    _persist_v3_trace(run_id=report.run_id, trace_events=trace_events)
    return {
        "report": report,
        "planning": planning_result,
        "inspection": inspection,
        "events": [event.model_dump(mode="json") for event in event_store.list()] if include_events else [],
        "trace": [event.model_dump(mode="json") for event in trace_events] if include_trace else [],
    }


async def plan_v3_graph(
    *,
    goal: str,
    workdir: str,
    skill_executor: SkillExecutor,
    rag_id: str | None = None,
    rag_ids: list[str] | None = None,
    coding_execution_mode: str = "internal",
    external_coding: dict[str, object] | None = None,
) -> PlanningResult:
    """Generate a graph for a V3 goal."""
    run_id = str(uuid4())
    planning_output = await skill_executor.execute(
        "planning",
        SkillInput(
            run_id=run_id,
            payload={
                "goal": goal,
                "workspace_root": workdir,
                "rag_id": rag_id,
                "rag_ids": rag_ids or [],
                "coding_execution_mode": coding_execution_mode,
                **(external_coding or {}),
            },
            context={"workspace_root": workdir},
        ),
    )
    if not planning_output.success:
        raise ValueError(planning_output.error or "planning failed")
    return PlanningResult.model_validate(planning_output.data)


async def inspect_v3_graph(
    *,
    goal: str | None = None,
    graph: TaskGraph | None = None,
    workdir: str | None = None,
    registry: SkillRegistry | None = None,
    rag_id: str | None = None,
    rag_ids: list[str] | None = None,
    coding_execution_mode: str = "internal",
    external_coding: dict[str, object] | None = None,
) -> tuple[GraphInspection, PlanningResult | None]:
    """Inspect a V3 graph or a planner-generated graph without executing it."""
    resolved_workdir = str(Path(workdir or ".").expanduser().resolve())
    skill_registry = registry or build_default_skill_registry(workspace_root=resolved_workdir)
    planning_result: PlanningResult | None = None
    resolved_graph = graph

    if resolved_graph is None:
        if not (goal or "").strip():
            raise ValueError("必须提供 graph 或 goal。")
        planning_result = await plan_v3_graph(
            goal=goal or "",
            workdir=resolved_workdir,
            skill_executor=SkillExecutor(skill_registry),
            rag_id=rag_id,
            rag_ids=rag_ids,
            coding_execution_mode=coding_execution_mode,
            external_coding=external_coding,
        )
        resolved_graph = planning_result.graph

    inspection = build_graph_inspection(resolved_graph)
    return inspection, planning_result


def format_v3_result(
    *,
    report: ExecutionReport | None,
    planning: PlanningResult | None = None,
    inspection: GraphInspection | None = None,
    events: list[dict[str, object]] | None = None,
    trace: list[dict[str, object]] | None = None,
) -> str:
    """Format a V3 result for the shared CLI."""
    if report is None:
        lines = ["Answer:", "plan_only=true", "", "Version: v3"]
        if planning is not None:
            lines.extend(
                [
                    f"Graph ID: {planning.graph.graph_id}",
                    f"Goal Kind: {planning.goal_kind}",
                    f"Repo Profile: {planning.repo_profile}",
                    f"Recovery Strategy: {planning.recovery_strategy.value}",
                    f"Coding Mode: {planning.coding_execution_mode}",
                    f"RAG IDs: {planning.rag_ids or ([planning.rag_id] if planning.rag_id else [])}",
                    f"Template: {planning.template_name}",
                ]
            )
        if inspection is not None:
            lines.extend(
                [
                    f"Node Count: {inspection.node_count}",
                    f"Execution Layers: {inspection.execution_layers}",
                ]
            )
        return "\n".join(lines)

    lines = [
        "Answer:",
        report.model_dump_json(indent=2),
        "",
        "Version: v3",
        f"Run ID: {report.run_id}",
        f"Graph ID: {report.graph_id}",
        f"Status: {report.status.value}",
        f"Completed Nodes: {', '.join(report.completed_node_ids) or '-'}",
        f"Failed Nodes: {', '.join(report.failed_node_ids) or '-'}",
        f"Recovered Nodes: {', '.join(report.recovered_node_ids) or '-'}",
        f"Skipped Nodes: {', '.join(report.skipped_node_ids) or '-'}",
    ]
    planning = report.shared_state.get("planning")
    if isinstance(planning, dict):
        lines.extend(
            [
                f"Goal Kind: {planning.get('goal_kind') or '-'}",
                f"Repo Profile: {planning.get('repo_profile') or '-'}",
                f"Recovery Strategy: {planning.get('recovery_strategy') or '-'}",
                f"Coding Mode: {planning.get('coding_execution_mode') or '-'}",
                f"RAG IDs: {planning.get('rag_ids') or ([planning.get('rag_id')] if planning.get('rag_id') else []) or '-'}",
                f"Template: {planning.get('template_name') or '-'}",
                f"Execution Layers: {planning.get('execution_layers') or '-'}",
            ]
        )
    if trace:
        lines.extend(["", "Trace:"])
        lines.extend(f"- {item.get('event_type')}: {item.get('message')}" for item in trace)
    if events:
        lines.extend(["", f"Event Count: {len(events)}"])
    return "\n".join(lines)


def build_graph_inspection(graph: TaskGraph) -> GraphInspection:
    """Build a validated inspection summary for a graph."""
    GraphValidator().validate(graph)
    node_ids = [node.node_id for node in graph.nodes]
    dependency_map = {node.node_id: list(node.dependencies) for node in graph.nodes}
    dependents_map: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for node_id, dependencies in dependency_map.items():
        for dependency in dependencies:
            dependents_map[dependency].append(node_id)

    root_node_ids = [node_id for node_id, dependencies in dependency_map.items() if not dependencies]
    leaf_node_ids = [node_id for node_id, dependents in dependents_map.items() if not dependents]
    execution_layers = _compute_execution_layers(dependency_map)

    return GraphInspection(
        graph=graph,
        is_valid=True,
        node_count=len(graph.nodes),
        edge_count=sum(len(node.dependencies) for node in graph.nodes),
        root_node_ids=root_node_ids,
        leaf_node_ids=leaf_node_ids,
        execution_layers=execution_layers,
    )


def _persist_v3_trace(*, run_id: str, trace_events: list[TraceEvent]) -> None:
    """Persist V3 trace events into the shared trace backends."""
    if not trace_events:
        return
    repository = SQLiteTraceRepository(SQLiteDB())
    recorder = JsonlTraceRecorder(run_id=run_id)
    repository.save_events(run_id, trace_events)
    recorder.record_many(trace_events)


def _attach_trigger_engine(
    *,
    event_bus: EventBus,
    event_store: EventStore,
    execution_nodes: list[ExecutionNode],
    diagnostics: list[TriggerDiagnostic],
    trigger_rules: list[TriggerRule],
    skill_executor: SkillExecutor,
) -> None:
    """Attach a trigger engine to the event bus for configured rules."""
    if not trigger_rules:
        return
    trigger_registry = TriggerRegistry()
    for rule in trigger_rules:
        trigger_registry.register(rule)
    trigger_engine = TriggerEngine(
        trigger_registry,
        skill_executor,
        event_bus=event_bus,
        event_store=event_store,
        execution_nodes=execution_nodes,
        diagnostics=diagnostics,
    )
    for event_type in {rule.event_type for rule in trigger_rules if rule.enabled}:
        event_bus.subscribe(event_type, trigger_engine.handle_event)


def _compute_execution_layers(dependency_map: dict[str, list[str]]) -> list[list[str]]:
    remaining = {node_id: set(dependencies) for node_id, dependencies in dependency_map.items()}
    layers: list[list[str]] = []

    while remaining:
        ready = sorted(node_id for node_id, dependencies in remaining.items() if not dependencies)
        if not ready:
            raise ValueError("Graph inspection failed because the graph is not a DAG")
        layers.append(ready)
        for node_id in ready:
            remaining.pop(node_id, None)
        for dependencies in remaining.values():
            dependencies.difference_update(ready)

    return layers
