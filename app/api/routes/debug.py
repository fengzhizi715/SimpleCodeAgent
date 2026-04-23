"""调试与健康检查接口。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_trace_repository, get_v2_runtime
from app.core.config import settings

router = APIRouter(tags=["debug"])


class HealthResponse(BaseModel):
    """健康检查响应。"""

    model_config = ConfigDict(extra="forbid")

    status: str
    app_name: str
    env: str


class TraceQueryResponse(BaseModel):
    """Trace 查询响应。"""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    events: list[dict[str, object]] = Field(default_factory=list)


class RootTraceQueryResponse(BaseModel):
    """按 root_run_id 查询 Trace 的响应，聚合整棵运行树。"""

    model_config = ConfigDict(extra="forbid")

    root_run_id: str
    events: list[dict[str, object]] = Field(default_factory=list)


class RunReplayResponse(BaseModel):
    """V2 单次运行回放响应。"""

    model_config = ConfigDict(extra="forbid")

    run: dict[str, object]
    workspace: dict[str, object] | None = None
    delegations: list[dict[str, object]] = Field(default_factory=list)
    artifacts: list[dict[str, object]] = Field(default_factory=list)
    trace: list[dict[str, object]] = Field(default_factory=list)
    execution_log: list[dict[str, object]] = Field(default_factory=list)
    delegation_tree: list[dict[str, object]] = Field(default_factory=list)
    execution_nodes: list[dict[str, object]] = Field(default_factory=list)
    teaching_view: dict[str, object] = Field(default_factory=dict)


class SessionReplayResponse(BaseModel):
    """V2 session 聚合回放响应。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    runs: list[dict[str, object]] = Field(default_factory=list)
    workspaces: list[dict[str, object]] = Field(default_factory=list)
    delegations: list[dict[str, object]] = Field(default_factory=list)
    artifacts: list[dict[str, object]] = Field(default_factory=list)
    trace: list[dict[str, object]] = Field(default_factory=list)
    execution_log: list[dict[str, object]] = Field(default_factory=list)
    delegation_tree: list[dict[str, object]] = Field(default_factory=list)
    execution_nodes: list[dict[str, object]] = Field(default_factory=list)
    teaching_view: dict[str, object] = Field(default_factory=dict)


@router.get("/healthz", response_model=HealthResponse, status_code=status.HTTP_200_OK)
def healthz() -> HealthResponse:
    """返回服务健康状态。"""
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        env=settings.app_env,
    )


@router.get("/debug/traces/{run_id}", response_model=TraceQueryResponse, status_code=status.HTTP_200_OK)
def get_trace(run_id: str) -> TraceQueryResponse:
    """按 run_id 查询 Trace 时间线。"""
    events = get_trace_repository().query_timeline(run_id)
    if not events:
        raise HTTPException(status_code=404, detail=f"未找到 run_id={run_id} 的 trace。")
    return TraceQueryResponse(
        run_id=run_id,
        events=[event.model_dump() for event in events],
    )


@router.get("/debug/traces-root/{root_run_id}", response_model=RootTraceQueryResponse, status_code=status.HTTP_200_OK)
def get_root_trace(root_run_id: str) -> RootTraceQueryResponse:
    """按 root_run_id 查询整棵运行树的 Trace 时间线，用于追踪 PlanExecutor 的完整执行流。"""
    events = get_trace_repository().query_timeline_by_root(root_run_id)
    if not events:
        raise HTTPException(status_code=404, detail=f"未找到 root_run_id={root_run_id} 的 trace。")
    return RootTraceQueryResponse(
        root_run_id=root_run_id,
        events=[event.model_dump() for event in events],
    )


@router.get("/debug/v2/runs/{run_id}/replay", response_model=RunReplayResponse, status_code=status.HTTP_200_OK)
def get_v2_run_replay(run_id: str) -> RunReplayResponse:
    """按 run_id 查询 V2 的回放视图。"""
    replay = get_v2_runtime().get_run_replay(run_id)
    if not replay or not replay.get("run"):
        raise HTTPException(status_code=404, detail=f"未找到 run_id={run_id} 的 v2 replay。")
    return RunReplayResponse.model_validate(replay)


@router.get("/debug/v2/sessions/{session_id}/replay", response_model=SessionReplayResponse, status_code=status.HTTP_200_OK)
def get_v2_session_replay(session_id: str) -> SessionReplayResponse:
    """按 session_id 查询 V2 的聚合回放视图。"""
    replay = get_v2_runtime().get_session_replay(session_id)
    if not replay or not replay.get("runs"):
        raise HTTPException(status_code=404, detail=f"未找到 session_id={session_id} 的 v2 replay。")
    return SessionReplayResponse.model_validate(replay)
