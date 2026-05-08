"""V3 HTTP routes in the shared API layer."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.v3.contracts.execution_contracts import ExecutionReport
from app.v3.contracts.graph_contracts import GraphInspection, TaskGraph
from app.v3.contracts.planning_contracts import PlanningResult
from app.v3.runner import inspect_v3_graph, plan_v3_graph, run_v3
from app.v3.runtime.skill_executor import SkillExecutor
from app.v3 import build_default_skill_registry

router = APIRouter(prefix="/v3", tags=["v3"])


class V3RunRequest(BaseModel):
    """Request for running a V3 graph or goal."""

    model_config = ConfigDict(extra="forbid")

    goal: str | None = Field(default=None, description="Optional high-level goal used by the planning skill.")
    graph: TaskGraph | None = Field(default=None, description="Optional explicit graph to execute.")
    workdir: str | None = Field(default=None, description="Optional workspace root for planner and test runner.")
    plan_only: bool = Field(default=False, description="Return planning/inspection only without execution.")
    include_events: bool = Field(default=True, description="Whether to include local event records in the response.")
    include_trace: bool = Field(default=True, description="Whether to include converted trace records in the response.")


class V3RunResponse(BaseModel):
    """Response for a V3 graph run."""

    model_config = ConfigDict(extra="forbid")

    report: ExecutionReport | None = None
    planning: PlanningResult | None = None
    inspection: GraphInspection | None = None
    events: list[dict[str, object]] = Field(default_factory=list)
    trace: list[dict[str, object]] = Field(default_factory=list)


class V3PlanRequest(BaseModel):
    """Request for generating a V3 plan without execution."""

    model_config = ConfigDict(extra="forbid")

    goal: str = Field(description="High-level goal used by the planning skill.")
    workdir: str | None = Field(default=None, description="Optional workspace root for planner inspection.")


class V3PlanResponse(BaseModel):
    """Structured V3 planning response."""

    model_config = ConfigDict(extra="forbid")

    planning: PlanningResult


class V3InspectGraphRequest(BaseModel):
    """Request for graph inspection without execution."""

    model_config = ConfigDict(extra="forbid")

    goal: str | None = Field(default=None, description="Optional goal used to generate a graph before inspection.")
    graph: TaskGraph | None = Field(default=None, description="Optional explicit graph to inspect.")
    workdir: str | None = Field(default=None, description="Optional workspace root for planner inspection.")


class V3InspectGraphResponse(BaseModel):
    """Graph inspection response for V3."""

    model_config = ConfigDict(extra="forbid")

    inspection: GraphInspection
    planning: PlanningResult | None = None


@router.post("/run", response_model=V3RunResponse, status_code=status.HTTP_200_OK)
async def run_v3_route(request: V3RunRequest) -> V3RunResponse:
    """Run a V3 graph or a planned goal."""
    try:
        result = await run_v3(
            goal=request.goal,
            graph=request.graph,
            workdir=request.workdir,
            plan_only=request.plan_only,
            include_events=request.include_events,
            include_trace=request.include_trace,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return V3RunResponse(
        report=result["report"],
        planning=result.get("planning"),
        inspection=result.get("inspection"),
        events=result["events"],
        trace=result["trace"],
    )


@router.post("/plan", response_model=V3PlanResponse, status_code=status.HTTP_200_OK)
async def plan_v3_route(request: V3PlanRequest) -> V3PlanResponse:
    """Generate a V3 plan without executing it."""
    try:
        skill_executor = SkillExecutor(
            build_default_skill_registry(workspace_root=request.workdir or ".")
        )
        planning = await plan_v3_graph(
            goal=request.goal,
            workdir=request.workdir or ".",
            skill_executor=skill_executor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return V3PlanResponse(planning=planning)


@router.post("/inspect-graph", response_model=V3InspectGraphResponse, status_code=status.HTTP_200_OK)
async def inspect_v3_graph_route(request: V3InspectGraphRequest) -> V3InspectGraphResponse:
    """Inspect a V3 graph or planner-generated graph without executing it."""
    try:
        inspection, planning = await inspect_v3_graph(
            goal=request.goal,
            graph=request.graph,
            workdir=request.workdir,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return V3InspectGraphResponse(
        inspection=inspection,
        planning=planning,
    )
