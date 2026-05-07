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
from app.v3.contracts.execution_contracts import ExecutionReport
from app.v3.contracts.graph_contracts import TaskGraph
from app.v3.contracts.skill_contracts import SkillInput
from app.v3.events.event_bus import EventBus
from app.v3.events.event_store import EventStore
from app.v3.graph.graph_builder import GraphBuilder
from app.v3.graph.graph_validator import GraphValidator
from app.v3.runtime.execution_kernel import ExecutionKernel
from app.v3.runtime.graph_executor import GraphExecutor
from app.v3.runtime.skill_executor import SkillExecutor
from app.v3.trace import attach_trace_collector


async def run_v3(
    *,
    goal: str | None = None,
    graph: TaskGraph | None = None,
    workdir: str | None = None,
    include_events: bool = True,
    include_trace: bool = True,
) -> dict[str, Any]:
    """Run a V3 goal or graph and return serializable output."""
    resolved_workdir = str(Path(workdir or ".").expanduser().resolve())
    event_bus = EventBus()
    event_store = EventStore()
    trace_events = attach_trace_collector(event_bus)
    registry = build_default_skill_registry(workspace_root=resolved_workdir)
    skill_executor = SkillExecutor(registry)
    graph_executor = GraphExecutor(skill_executor, event_bus=event_bus, event_store=event_store)
    kernel = ExecutionKernel(
        graph_executor=graph_executor,
        validator=GraphValidator(),
        event_bus=event_bus,
        event_store=event_store,
    )

    resolved_graph = graph
    if resolved_graph is None:
        if not (goal or "").strip():
            raise ValueError("必须提供 graph 或 goal。")
        resolved_graph = await plan_v3_graph(
            goal=goal or "",
            workdir=resolved_workdir,
            skill_executor=skill_executor,
        )

    context = await kernel.run_graph(
        resolved_graph,
        initial_shared_state={"workspace_root": resolved_workdir},
    )
    report = context.to_report(resolved_graph)
    _persist_v3_trace(run_id=report.run_id, trace_events=trace_events)
    return {
        "report": report,
        "events": [event.model_dump(mode="json") for event in event_store.list()] if include_events else [],
        "trace": [event.model_dump(mode="json") for event in trace_events] if include_trace else [],
    }


async def plan_v3_graph(
    *,
    goal: str,
    workdir: str,
    skill_executor: SkillExecutor,
) -> TaskGraph:
    """Generate a graph for a V3 goal."""
    run_id = str(uuid4())
    planning_output = await skill_executor.execute(
        "planning",
        SkillInput(
            run_id=run_id,
            payload={"goal": goal, "workspace_root": workdir},
            context={"workspace_root": workdir},
        ),
    )
    if not planning_output.success:
        raise ValueError(planning_output.error or "planning failed")
    return GraphBuilder().from_payload(planning_output.data["graph"])


def format_v3_result(
    *,
    report: ExecutionReport,
    events: list[dict[str, object]] | None = None,
    trace: list[dict[str, object]] | None = None,
) -> str:
    """Format a V3 result for the shared CLI."""
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
        f"Skipped Nodes: {', '.join(report.skipped_node_ids) or '-'}",
    ]
    if trace:
        lines.extend(["", "Trace:"])
        lines.extend(f"- {item.get('event_type')}: {item.get('message')}" for item in trace)
    if events:
        lines.extend(["", f"Event Count: {len(events)}"])
    return "\n".join(lines)


def _persist_v3_trace(*, run_id: str, trace_events: list[TraceEvent]) -> None:
    """Persist V3 trace events into the shared trace backends."""
    if not trace_events:
        return
    repository = SQLiteTraceRepository(SQLiteDB())
    recorder = JsonlTraceRecorder(run_id=run_id)
    repository.save_events(run_id, trace_events)
    recorder.record_many(trace_events)
