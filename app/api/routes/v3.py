"""V3 HTTP routes in the shared API layer."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.v3.contracts.execution_contracts import ExecutionReport
from app.v3.contracts.graph_contracts import TaskGraph
from app.v3.runner import run_v3

router = APIRouter(prefix="/v3", tags=["v3"])


class V3RunRequest(BaseModel):
    """Request for running a V3 graph or goal."""

    model_config = ConfigDict(extra="forbid")

    goal: str | None = Field(default=None, description="Optional high-level goal used by the planning skill.")
    graph: TaskGraph | None = Field(default=None, description="Optional explicit graph to execute.")
    workdir: str | None = Field(default=None, description="Optional workspace root for planner and test runner.")
    include_events: bool = Field(default=True, description="Whether to include local event records in the response.")
    include_trace: bool = Field(default=True, description="Whether to include converted trace records in the response.")


class V3RunResponse(BaseModel):
    """Response for a V3 graph run."""

    model_config = ConfigDict(extra="forbid")

    report: ExecutionReport
    events: list[dict[str, object]] = Field(default_factory=list)
    trace: list[dict[str, object]] = Field(default_factory=list)


@router.post("/run", response_model=V3RunResponse, status_code=status.HTTP_200_OK)
async def run_v3_route(request: V3RunRequest) -> V3RunResponse:
    """Run a V3 graph or a planned goal."""
    try:
        result = await run_v3(
            goal=request.goal,
            graph=request.graph,
            workdir=request.workdir,
            include_events=request.include_events,
            include_trace=request.include_trace,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return V3RunResponse(
        report=result["report"],
        events=result["events"],
        trace=result["trace"],
    )
