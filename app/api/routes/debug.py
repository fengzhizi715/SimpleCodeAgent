"""调试与健康检查接口。"""

from __future__ import annotations

import base64
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_trace_repository, get_v2_runtime
from app.core.config import BASE_DIR, settings
from app.v1.rag.vector_store import ChromaVectorStore
from app.v1.rag.ingest import DocsIngestor

router = APIRouter(tags=["debug"])


class HealthResponse(BaseModel):
    """健康检查响应。"""

    model_config = ConfigDict(extra="forbid")

    status: str
    app_name: str
    env: str
    llm_base_url: str = ""
    llm_model: str = ""


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


class V2RunHistoryItem(BaseModel):
    """单次运行在历史列表中的摘要（当前接口仅返回含 workspace 的 V2；agent_version 为扩展字段）。"""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    session_id: str
    model: str
    task: str
    agent_version: str = Field(default="v2", description="Agent 版本：v1 / v2 / v3 …")
    status: str | None = None
    step_count: int = 0
    final_output: str = ""
    created_at: str
    updated_at: str
    user_goal: str = ""


class V2RunHistoryResponse(BaseModel):
    """V2 运行历史列表响应。"""

    model_config = ConfigDict(extra="forbid")

    total: int = 0
    limit: int = 50
    offset: int = 0
    runs: list[V2RunHistoryItem] = Field(default_factory=list)


class V2DeleteRunResponse(BaseModel):
    """V2 删除运行记录响应。"""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    deleted: bool


class AgentCatalogItem(BaseModel):
    """当前可用智能体条目。"""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    role: str
    description: str
    capabilities: list[str] = Field(default_factory=list)
    availability: str = "enabled"


class AgentCatalogResponse(BaseModel):
    """智能体目录响应。"""

    model_config = ConfigDict(extra="forbid")

    total: int = 0
    agents: list[AgentCatalogItem] = Field(default_factory=list)


class RagFileItem(BaseModel):
    """RAG 文件分布统计项。"""

    model_config = ConfigDict(extra="forbid")

    source: str
    chunk_count: int


class RagOverviewResponse(BaseModel):
    """RAG 向量库概览。"""

    model_config = ConfigDict(extra="forbid")

    backend: str
    collection_name: str
    persist_dir: str
    embedding_provider: str
    embedding_model: str
    embedding_base_url: str
    total_chunks: int
    file_count: int
    limit: int
    offset: int
    sampled_chunk_count: int
    files: list[RagFileItem] = Field(default_factory=list)


class RagDeleteSourceRequest(BaseModel):
    """按 source 删除 RAG 分块请求。"""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, description="待删除文件 source。")


class RagDeleteSourceResponse(BaseModel):
    """按 source 删除 RAG 分块响应。"""

    model_config = ConfigDict(extra="forbid")

    source: str
    deleted_chunks: int


class RagReindexSourceRequest(BaseModel):
    """按 source 重建索引请求。"""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, description="待重建索引文件 source。")


class RagReindexSourceResponse(BaseModel):
    """按 source 重建索引响应。"""

    model_config = ConfigDict(extra="forbid")

    source: str
    deleted_chunks: int
    ingested_chunks: int


class RagUploadResponse(BaseModel):
    """上传并导入单文件响应。"""

    model_config = ConfigDict(extra="forbid")

    source: str
    ingested_chunks: int


class RagUploadRequest(BaseModel):
    """上传文件内容请求。"""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, description="文件名。")
    content_base64: str = Field(min_length=1, description="文件二进制内容的 base64 字符串。")
    source_dir: str = Field(default="uploads", description="写入 docs 下的子目录。")


@router.get("/healthz", response_model=HealthResponse, status_code=status.HTTP_200_OK)
def healthz() -> HealthResponse:
    """返回服务健康状态。"""
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        env=settings.app_env,
        llm_base_url=settings.llm_base_url,
        llm_model=settings.llm_model,
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


@router.get("/debug/v2/runs", response_model=V2RunHistoryResponse, status_code=status.HTTP_200_OK)
def list_v2_runs(
    limit: int = Query(default=50, ge=1, le=200, description="返回条数上限。"),
    offset: int = Query(default=0, ge=0, description="分页偏移。"),
) -> V2RunHistoryResponse:
    """列出最近运行历史（兼容旧路径，包含 v1/v2 顶层运行）。"""
    total = get_v2_runtime().count_runs_for_ui()
    rows = get_v2_runtime().list_recent_runs_for_ui(limit=limit, offset=offset)
    return V2RunHistoryResponse(
        total=total,
        limit=limit,
        offset=offset,
        runs=[V2RunHistoryItem.model_validate(row) for row in rows],
    )


@router.get("/debug/runs", response_model=V2RunHistoryResponse, status_code=status.HTTP_200_OK)
def list_runs(
    limit: int = Query(default=50, ge=1, le=200, description="返回条数上限。"),
    offset: int = Query(default=0, ge=0, description="分页偏移。"),
) -> V2RunHistoryResponse:
    """列出最近运行历史，默认隐藏 v1 planner/direct-tool 内部子 run。"""
    return list_v2_runs(limit=limit, offset=offset)


@router.get("/debug/agents", response_model=AgentCatalogResponse, status_code=status.HTTP_200_OK)
def list_agents() -> AgentCatalogResponse:
    """列出当前运行时注册的智能体。"""
    specs = get_v2_runtime().registry.list_specs()
    agents = [
        AgentCatalogItem(
            agent_id=spec.agent_id,
            role=spec.role,
            description=spec.description,
            capabilities=list(spec.capabilities),
            availability=spec.availability,
        )
        for spec in specs
    ]
    return AgentCatalogResponse(total=len(agents), agents=agents)


@router.delete("/debug/v2/runs/{run_id}", response_model=V2DeleteRunResponse, status_code=status.HTTP_200_OK)
def delete_v2_run(run_id: str) -> V2DeleteRunResponse:
    """删除单条 run 及其关联回放数据（兼容旧路径）。"""
    deleted = get_v2_runtime().delete_run_for_ui(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"未找到 run_id={run_id}。")
    return V2DeleteRunResponse(run_id=run_id, deleted=True)


@router.delete("/debug/runs/{run_id}", response_model=V2DeleteRunResponse, status_code=status.HTTP_200_OK)
def delete_run(run_id: str) -> V2DeleteRunResponse:
    """删除单条 run 及其关联回放数据。"""
    return delete_v2_run(run_id)


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


@router.get("/debug/rag/overview", response_model=RagOverviewResponse, status_code=status.HTTP_200_OK)
def get_rag_overview(
    limit: int = Query(default=20, ge=1, le=200, description="每页文件数量。"),
    offset: int = Query(default=0, ge=0, description="分页偏移。"),
) -> RagOverviewResponse:
    """返回当前 Chroma 向量库概览，供 Web UI 展示。"""
    vector_store = ChromaVectorStore()
    overview = vector_store.inspect()

    embedding_model = getattr(settings, "embedding_model", "") or "local-hash"
    embedding_api_key = getattr(settings, "embedding_api_key", "")
    embedding_base_url = getattr(settings, "embedding_base_url", settings.llm_base_url)
    embedding_provider = "openai-compatible" if embedding_model != "local-hash" and bool(embedding_api_key) else "local-hash"

    all_files = overview["files"]
    paged_files = all_files[offset : offset + limit]

    return RagOverviewResponse(
        backend="chroma",
        collection_name=overview["collection_name"],
        persist_dir=overview["persist_dir"],
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        embedding_base_url=embedding_base_url,
        total_chunks=overview["total_chunks"],
        file_count=overview["file_count"],
        limit=limit,
        offset=offset,
        sampled_chunk_count=overview["sampled_chunk_count"],
        files=[RagFileItem.model_validate(item) for item in paged_files],
    )


@router.post("/debug/rag/delete-source", response_model=RagDeleteSourceResponse, status_code=status.HTTP_200_OK)
def delete_rag_source(request: RagDeleteSourceRequest) -> RagDeleteSourceResponse:
    """按 source 删除向量库中的文档分块。"""
    source = request.source.strip()
    if not source:
        raise HTTPException(status_code=400, detail="source 不能为空。")
    vector_store = ChromaVectorStore()
    deleted_chunks = vector_store.delete_by_source(source)
    return RagDeleteSourceResponse(source=source, deleted_chunks=deleted_chunks)


@router.post("/debug/rag/reindex-source", response_model=RagReindexSourceResponse, status_code=status.HTTP_200_OK)
def reindex_rag_source(request: RagReindexSourceRequest) -> RagReindexSourceResponse:
    """按 source 删除旧分块后重建索引。"""
    source = request.source.strip()
    if not source:
        raise HTTPException(status_code=400, detail="source 不能为空。")

    target_path = (BASE_DIR / source).resolve()
    base_dir_resolved = BASE_DIR.resolve()
    if base_dir_resolved not in target_path.parents:
        raise HTTPException(status_code=400, detail="source 非法，必须位于仓库目录内。")
    if not target_path.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {source}")

    vector_store = ChromaVectorStore()
    try:
        deleted_chunks = vector_store.delete_by_source(source)
        ingested_chunks = DocsIngestor(vector_store=vector_store).ingest_file(target_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return RagReindexSourceResponse(
        source=source,
        deleted_chunks=deleted_chunks,
        ingested_chunks=ingested_chunks,
    )


@router.post("/debug/rag/upload", response_model=RagUploadResponse, status_code=status.HTTP_200_OK)
def upload_rag_file(request: RagUploadRequest) -> RagUploadResponse:
    """上传文件并导入 Chroma。"""
    filename = Path(request.filename or "").name
    if not filename:
        raise HTTPException(status_code=400, detail="文件名不能为空。")

    docs_root = (BASE_DIR / "docs").resolve()
    target_subdir = request.source_dir.strip().strip("/").strip() or "uploads"
    target_dir = (docs_root / target_subdir).resolve()
    if docs_root not in target_dir.parents and target_dir != docs_root:
        raise HTTPException(status_code=400, detail="source_dir 非法，必须位于 docs 目录内。")
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename

    try:
        content = base64.b64decode(request.content_base64, validate=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="content_base64 非法。") from exc

    try:
        target_path.write_bytes(content)
        ingested_chunks = DocsIngestor().ingest_file(target_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    source = str(target_path.relative_to(BASE_DIR.resolve()))
    return RagUploadResponse(source=source, ingested_chunks=ingested_chunks)
