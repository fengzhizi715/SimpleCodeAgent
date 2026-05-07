"""V3 HTTP routes."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.v3 import build_default_skill_registry
from app.v3.contracts.event_contracts import V3Event
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
from app.v3.trace.v3_trace import V3TraceCollector

router = APIRouter(prefix="/v3", tags=["v3"])


class V3RunRequest(BaseModel):
    """Request for running a V3 graph or goal."""

    model_config = ConfigDict(extra="forbid")

    goal: str | None = Field(default=None, description="Optional high-level goal used by the planning skill.")
    graph: TaskGraph | None = Field(default=None, description="Optional explicit graph to execute.")
    include_events: bool = Field(default=True, description="Whether to include local event records in the response.")
    include_trace: bool = Field(default=True, description="Whether to include converted trace records in the response.")


class V3RunResponse(BaseModel):
    """Response for a V3 graph run."""

    model_config = ConfigDict(extra="forbid")

    report: ExecutionReport
    events: list[dict[str, object]] = Field(default_factory=list)
    trace: list[dict[str, object]] = Field(default_factory=list)


@router.post("/run", response_model=V3RunResponse, status_code=status.HTTP_200_OK)
async def run_v3(request: V3RunRequest) -> V3RunResponse:
    """Run a V3 graph or a planned goal."""
    if request.graph is None and not (request.goal or "").strip():
        raise HTTPException(status_code=400, detail="必须提供 graph 或 goal。")

    event_bus = EventBus()
    event_store = EventStore()
    trace_collector = V3TraceCollector()
    registry = build_default_skill_registry()
    skill_executor = SkillExecutor(registry)
    graph_executor = GraphExecutor(skill_executor, event_bus=event_bus, event_store=event_store)
    kernel = ExecutionKernel(
        graph_executor=graph_executor,
        validator=GraphValidator(),
        event_bus=event_bus,
        event_store=event_store,
    )

    async def trace_handler(event: V3Event) -> None:
        trace_collector.record(event)

    for event_type in [
        "graph_started",
        "graph_finished",
        "skill_started",
        "skill_finished",
        "skill_failed",
        "test_failed",
        "code_updated",
    ]:
        event_bus.subscribe(event_type, trace_handler)

    graph = request.graph
    if graph is None:
        run_id = str(uuid4())
        planning_output = await skill_executor.execute(
            "planning",
            SkillInput(
                run_id=run_id,
                payload={"goal": request.goal or ""},
                context={},
            ),
        )
        if not planning_output.success:
            raise HTTPException(status_code=500, detail=planning_output.error or "planning failed")
        graph = GraphBuilder().from_payload(planning_output.data["graph"])

    try:
        context = await kernel.run_graph(graph)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return V3RunResponse(
        report=context.to_report(graph),
        events=[event.model_dump(mode="json") for event in event_store.list()] if request.include_events else [],
        trace=[event.model_dump(mode="json") for event in trace_collector.list()] if request.include_trace else [],
    )
