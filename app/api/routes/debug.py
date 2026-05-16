"""调试与健康检查接口。"""

from __future__ import annotations

import base64
from time import perf_counter
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.api.deps import get_provider, get_trace_repository, get_v2_runtime
from app.contracts.message import ChatMessage
from app.contracts.run import RunRequest
from app.core.config import (
    BASE_DIR,
    get_effective_llm_base_url,
    get_effective_llm_model,
    settings,
    update_llm_runtime_settings,
)
from app.core.exceptions import RagIdValidationError
from app.llm.client import LLMProviderError
from app.trace.viewer import (
    load_and_format_root_timeline,
    load_and_format_session_timeline,
    load_and_format_timeline,
)
from app.db.sqlite import SQLiteDB
from app.v1.rag.config_store import RagConfigStore, RagIndexConfig
from app.v1.rag.ingest import DocsIngestor
from app.v1.rag.rag_id_policy import strict_normalize_v2_rag_ids, strict_normalize_v2_rag_tokens
from app.v1.rag.vector_store import ChromaVectorStore
from app.v3 import build_default_skill_registry
from app.v3.contracts.event_contracts import V3Event
from app.v3.contracts.replay_contracts import ReplayResult
from app.v3.events.event_history import EventChainItem, EventChainTrace, build_event_chain_trace, format_event_chain_trace
from app.v3.replay import replay_event_chain

router = APIRouter(tags=["debug"])


def _normalize_debug_rag_id(rag_id: str | None) -> str:
    """Debug RAG endpoints use V2's strict external rag_id contract."""
    try:
        return strict_normalize_v2_rag_ids(rag_id=rag_id, rag_ids=None)[0]
    except RagIdValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _load_v3_events_for_run(run_id: str) -> list[V3Event]:
    """Load V3 events from shared trace storage for one run."""
    trace_events = get_trace_repository().query_timeline(run_id)
    if not trace_events:
        raise HTTPException(status_code=404, detail=f"未找到 run_id={run_id} 的 trace。")

    v3_events: list[V3Event] = []
    for trace_event in trace_events:
        payload = trace_event.payload
        if not isinstance(payload, dict):
            continue
        try:
            v3_events.append(V3Event.model_validate(payload))
        except ValidationError:
            continue

    if not v3_events:
        raise HTTPException(status_code=404, detail=f"未找到 run_id={run_id} 的 v3 events。")
    return v3_events


def _resolve_v3_event_chain(
    *,
    run_id: str,
    execution_chain_id: str | None,
    event_id: str | None,
) -> EventChainTrace:
    """Resolve one V3 event chain by chain id or event id."""
    execution_chain_id = execution_chain_id.strip() if isinstance(execution_chain_id, str) else None
    event_id = event_id.strip() if isinstance(event_id, str) else None
    if bool(execution_chain_id) == bool(event_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="必须且只能提供 execution_chain_id 或 event_id 其中一个。",
        )

    v3_events = _load_v3_events_for_run(run_id)
    if event_id is not None:
        event = next((item for item in v3_events if item.event_id == event_id), None)
        if event is None:
            raise HTTPException(status_code=404, detail=f"未找到 event_id={event_id} 的 v3 event。")
        chain = build_event_chain_trace(
            v3_events,
            execution_chain_id=event.execution_chain_id or event.event_id,
            root_event_id=event_id,
        )
    else:
        chain = build_event_chain_trace(v3_events, execution_chain_id=str(execution_chain_id))

    if chain is None:
        detail = f"未找到 execution_chain_id={execution_chain_id} 的 v3 event chain。"
        if event_id is not None:
            detail = f"未找到以 event_id={event_id} 为根的 v3 event chain。"
        raise HTTPException(status_code=404, detail=detail)
    return chain


def _lookup_run_workdir(run_id: str) -> str | None:
    """Load persisted workdir for one run when available."""
    row = SQLiteDB().fetchone("SELECT workdir FROM runs WHERE run_id = ?", (run_id,))
    if row is None:
        return None
    value = row["workdir"]
    return str(value).strip() if value is not None and str(value).strip() else None


class HealthResponse(BaseModel):
    """健康检查响应。"""

    model_config = ConfigDict(extra="forbid")

    status: str
    app_name: str
    env: str
    llm_base_url: str = ""
    llm_model: str = ""


class LLMSettingsUpdateRequest(BaseModel):
    """更新全局 LLM 设置请求。"""

    model_config = ConfigDict(extra="forbid")

    llm_base_url: str = Field(min_length=1, description="新的 LLM_BASE_URL。")
    llm_model: str = Field(min_length=1, description="新的 LLM_MODEL。")


class LLMSettingsValidateResponse(BaseModel):
    """LLM 配置联通性校验响应。"""

    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    llm_base_url: str
    llm_model: str
    latency_ms: int
    message: str = "LLM 配置校验通过。"


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


class V3EventChainItemResponse(BaseModel):
    """V3 事件链条目响应。"""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: str
    source: str
    parent_event_id: str | None = None
    trigger_rule_id: str | None = None
    execution_chain_id: str
    trigger_depth: int = 0
    node_id: str | None = None
    summary: str | None = None
    error: str | None = None
    created_at: str


class V3EventChainTraceResponse(BaseModel):
    """V3 事件链查询响应。"""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    execution_chain_id: str
    root_event_id: str | None = None
    root_event_type: str | None = None
    item_count: int = 0
    items: list[V3EventChainItemResponse] = Field(default_factory=list)


class V3ReplayResponse(BaseModel):
    """V3 simple replay response."""

    model_config = ConfigDict(extra="forbid")

    metadata: dict[str, object]
    success: bool
    summary: str
    error: str | None = None
    output: dict[str, object] = Field(default_factory=dict)
    events: list[dict[str, object]] = Field(default_factory=list)
    trace: list[dict[str, object]] = Field(default_factory=list)


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


class RunDetailResponse(BaseModel):
    """统一 run 详情响应，按版本返回 V2/V3 所需内容。"""

    model_config = ConfigDict(extra="forbid")

    version: str
    run: dict[str, object]
    workspace: dict[str, object] | None = None
    delegations: list[dict[str, object]] = Field(default_factory=list)
    artifacts: list[dict[str, object]] = Field(default_factory=list)
    trace: list[dict[str, object]] = Field(default_factory=list)
    execution_log: list[dict[str, object]] = Field(default_factory=list)
    delegation_tree: list[dict[str, object]] = Field(default_factory=list)
    execution_nodes: list[dict[str, object]] = Field(default_factory=list)
    teaching_view: dict[str, object] = Field(default_factory=dict)
    report: dict[str, object] | None = None
    planning: dict[str, object] | None = None
    trigger_diagnostics: list[dict[str, object]] = Field(default_factory=list)


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


class SkillCatalogItem(BaseModel):
    """当前可用 v3 skill 条目。"""

    model_config = ConfigDict(extra="forbid")

    skill_name: str
    description: str
    skill_type: str
    capabilities: list[str] = Field(default_factory=list)
    enabled: bool = True
    typical_use: str = ""
    template_names: list[str] = Field(default_factory=list)


class AgentCatalogResponse(BaseModel):
    """智能体目录响应。"""

    model_config = ConfigDict(extra="forbid")

    total: int = 0
    agents: list[AgentCatalogItem] = Field(default_factory=list)
    v2_agents: list[AgentCatalogItem] = Field(default_factory=list)
    v2_total: int = 0
    v3_skills: list[SkillCatalogItem] = Field(default_factory=list)
    v3_total: int = 0


class UsageSummaryResponse(BaseModel):
    """Token usage Dashboard 聚合响应。"""

    model_config = ConfigDict(extra="forbid")

    totals: dict[str, object] = Field(default_factory=dict)
    by_version: list[dict[str, object]] = Field(default_factory=list)
    by_model: list[dict[str, object]] = Field(default_factory=list)
    by_day: list[dict[str, object]] = Field(default_factory=list)
    recent_runs: list[dict[str, object]] = Field(default_factory=list)


class RagFileItem(BaseModel):
    """RAG 文件分布统计项。"""

    model_config = ConfigDict(extra="forbid")

    source: str
    chunk_count: int


class RagCollectionItem(BaseModel):
    """RAG 集合条目。"""

    model_config = ConfigDict(extra="forbid")

    rag_id: str
    collection_name: str


class RagCollectionsResponse(BaseModel):
    """可用 RAG 集合列表。"""

    model_config = ConfigDict(extra="forbid")

    total: int = 0
    items: list[RagCollectionItem] = Field(default_factory=list)


class RagCreateCollectionRequest(BaseModel):
    """新建（或确保存在）RAG 向量集合。"""

    model_config = ConfigDict(extra="forbid")

    rag_id: str = Field(
        min_length=1,
        max_length=64,
        description="知识库标识；将规范化为小写，仅保留字母数字、连字符与下划线。",
    )
    chunk_size: int = Field(default=800, ge=100, le=8000, description="文档切分窗口大小。")
    overlap: int = Field(default=120, ge=0, le=4000, description="相邻 chunk 的重叠长度。")

    @field_validator("rag_id", mode="before")
    @classmethod
    def _strip_rag_id(cls, value: object) -> str:
        return str(value).strip() if value is not None else ""


class RagCreateCollectionResponse(BaseModel):
    """创建 RAG 集合结果。"""

    model_config = ConfigDict(extra="forbid")

    rag_id: str
    collection_name: str
    chunk_size: int
    overlap: int


class RagDeleteCollectionResponse(BaseModel):
    """删除 RAG 集合结果。"""

    model_config = ConfigDict(extra="forbid")

    rag_id: str
    collection_name: str
    config_deleted: bool


class RagOverviewResponse(BaseModel):
    """RAG 向量库概览。"""

    model_config = ConfigDict(extra="forbid")

    backend: str
    rag_id: str
    collection_name: str
    persist_dir: str
    embedding_provider: str
    embedding_model: str
    embedding_base_url: str
    chunk_size: int
    overlap: int
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
    rag_id: str | None = Field(default=None, description="可选知识库标识；不传使用 default。")


class RagDeleteSourceResponse(BaseModel):
    """按 source 删除 RAG 分块响应。"""

    model_config = ConfigDict(extra="forbid")

    source: str
    rag_id: str
    deleted_chunks: int


class RagReindexSourceRequest(BaseModel):
    """按 source 重建索引请求。"""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, description="待重建索引文件 source。")
    rag_id: str | None = Field(default=None, description="可选知识库标识；不传使用 default。")


class RagReindexSourceResponse(BaseModel):
    """按 source 重建索引响应。"""

    model_config = ConfigDict(extra="forbid")

    source: str
    rag_id: str
    deleted_chunks: int
    ingested_chunks: int


class RagUploadResponse(BaseModel):
    """上传并导入单文件响应。"""

    model_config = ConfigDict(extra="forbid")

    source: str
    rag_id: str
    ingested_chunks: int


class RagUploadRequest(BaseModel):
    """上传文件内容请求。"""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, description="文件名。")
    content_base64: str = Field(min_length=1, description="文件二进制内容的 base64 字符串。")
    source_dir: str = Field(default="uploads", description="写入 docs 下的子目录。")
    rag_id: str | None = Field(default=None, description="可选知识库标识；不传使用 default。")


@router.get("/healthz", response_model=HealthResponse, status_code=status.HTTP_200_OK)
def healthz() -> HealthResponse:
    """返回服务健康状态。"""
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        env=settings.app_env,
        llm_base_url=get_effective_llm_base_url(),
        llm_model=get_effective_llm_model(),
    )


@router.post("/debug/settings/llm", response_model=HealthResponse, status_code=status.HTTP_200_OK)
def update_llm_settings(request: LLMSettingsUpdateRequest) -> HealthResponse:
    """更新全局 LLM_BASE_URL / LLM_MODEL（立即生效并写入 .env）。"""
    update_llm_runtime_settings(
        llm_base_url=request.llm_base_url,
        llm_model=request.llm_model,
    )
    return healthz()


@router.post(
    "/debug/settings/llm/validate",
    response_model=LLMSettingsValidateResponse,
    status_code=status.HTTP_200_OK,
)
def validate_llm_settings() -> LLMSettingsValidateResponse:
    """校验当前生效的 LLM 配置是否可调用（发起一次最小 chat 请求）。"""
    provider = get_provider()
    started = perf_counter()
    try:
        provider.chat(
            RunRequest(
                messages=[ChatMessage(role="user", content="ping")],
                model=get_effective_llm_model(),
                reasoning_mode="low",
                temperature=0.0,
                max_tokens=8,
            )
        )
    except (LLMProviderError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"LLM 配置校验失败：{exc}") from exc
    latency_ms = int((perf_counter() - started) * 1000)
    return LLMSettingsValidateResponse(
        ok=True,
        llm_base_url=get_effective_llm_base_url(),
        llm_model=get_effective_llm_model(),
        latency_ms=latency_ms,
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


@router.get(
    "/debug/traces/{run_id}/view",
    response_class=PlainTextResponse,
    status_code=status.HTTP_200_OK,
)
def get_trace_view(run_id: str) -> PlainTextResponse:
    """按 run_id 查询并返回格式化后的纯文本 Trace 时间线。"""
    try:
        rendered = load_and_format_timeline(get_trace_repository(), run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlainTextResponse(rendered)


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


@router.get(
    "/debug/traces-root/{root_run_id}/view",
    response_class=PlainTextResponse,
    status_code=status.HTTP_200_OK,
)
def get_root_trace_view(root_run_id: str) -> PlainTextResponse:
    """按 root_run_id 查询并返回格式化后的纯文本整树 Trace 时间线。"""
    try:
        rendered = load_and_format_root_timeline(get_trace_repository(), root_run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlainTextResponse(rendered)


@router.get(
    "/debug/traces-session/{session_id}/view",
    response_class=PlainTextResponse,
    status_code=status.HTTP_200_OK,
)
def get_session_trace_view(session_id: str) -> PlainTextResponse:
    """按 session_id 查询并返回格式化后的纯文本会话 Trace 时间线。"""
    try:
        rendered = load_and_format_session_timeline(get_trace_repository(), session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlainTextResponse(rendered)


@router.get(
    "/debug/v3/runs/{run_id}/event-chain",
    response_model=V3EventChainTraceResponse,
    status_code=status.HTTP_200_OK,
)
def get_v3_event_chain(
    run_id: str,
    execution_chain_id: str | None = Query(default=None, description="按 execution_chain_id 查询整条事件链。"),
    event_id: str | None = Query(default=None, description="按 event_id 查询以该事件为根的子链。"),
) -> V3EventChainTraceResponse:
    """按 execution_chain_id 或 event_id 查询可读的 V3 事件链。"""
    chain = _resolve_v3_event_chain(
        run_id=run_id,
        execution_chain_id=execution_chain_id,
        event_id=event_id,
    )
    return V3EventChainTraceResponse(
        run_id=chain.run_id,
        execution_chain_id=chain.execution_chain_id,
        root_event_id=chain.root_event_id,
        root_event_type=chain.root_event_type,
        item_count=len(chain.items),
        items=[V3EventChainItemResponse.model_validate(item.model_dump(mode="json")) for item in chain.items],
    )


@router.get(
    "/debug/v3/runs/{run_id}/event-chain/view",
    response_class=PlainTextResponse,
    status_code=status.HTTP_200_OK,
)
def get_v3_event_chain_view(
    run_id: str,
    execution_chain_id: str | None = Query(default=None, description="按 execution_chain_id 查询整条事件链。"),
    event_id: str | None = Query(default=None, description="按 event_id 查询以该事件为根的子链。"),
) -> PlainTextResponse:
    """按 execution_chain_id 或 event_id 查询格式化后的 V3 事件链文本视图。"""
    chain = _resolve_v3_event_chain(
        run_id=run_id,
        execution_chain_id=execution_chain_id,
        event_id=event_id,
    )
    return PlainTextResponse(format_event_chain_trace(chain))


@router.post(
    "/debug/v3/runs/{run_id}/event-chain/replay",
    response_model=V3ReplayResponse,
    status_code=status.HTTP_200_OK,
)
async def replay_v3_event_chain(
    run_id: str,
    event_id: str = Query(description="要作为 replay 入口的源事件 ID。"),
) -> V3ReplayResponse:
    """Replay a single V3 event chain entry by re-executing its first triggered skill."""
    repository = get_trace_repository()
    workdir = _lookup_run_workdir(run_id)
    try:
        result: ReplayResult = await replay_event_chain(
            repository=repository,
            run_id=run_id,
            event_id=event_id,
            workspace_root=workdir,
            registry=build_default_skill_registry(workspace_root=workdir),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return V3ReplayResponse(
        metadata=result.metadata.model_dump(mode="json"),
        success=result.success,
        summary=result.summary,
        error=result.error,
        output=result.output,
        events=result.events,
        trace=result.trace,
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
    """列出当前运行时注册的 v2 agents 与 v3 skills。"""
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
    skill_registry = build_default_skill_registry(workspace_root=BASE_DIR)
    skill_catalog_hints: dict[str, dict[str, object]] = {
        "planning": {
            "typical_use": "根据任务目标、仓库特征和 RAG 配置，生成适合当前场景的 graph 模板与恢复策略。",
            "template_names": [
                "analysis_only",
                "analysis_with_context",
                "testing_branch_verify",
                "coding_focus_then_full_suite",
                "default",
            ],
        },
        "retrieve_docs": {
            "typical_use": "在分析或改码前补充外部文档、知识库或多 RAG 检索上下文。",
            "template_names": [
                "analysis_with_context",
                "default",
            ],
        },
        "analyze_repo": {
            "typical_use": "抽取仓库画像、候选测试命令和测试目标，为后续 coding / testing 节点提供上下文。",
            "template_names": [
                "analysis_only",
                "analysis_with_context",
                "testing_branch_verify",
                "coding_focus_then_full_suite",
                "default",
            ],
        },
        "coding": {
            "typical_use": "执行真实改码动作，可切换 internal / external 后端，并承接 test_failed 之后的 fix-only 恢复。",
            "template_names": [
                "default",
                "coding_focus_then_full_suite",
                "template_fix_after_test_failed",
            ],
        },
        "test_runner": {
            "typical_use": "执行 focused test 或 full-suite verification，既能作为主链节点，也能作为恢复后的验证节点。",
            "template_names": [
                "default",
                "testing_branch_verify",
                "coding_focus_then_full_suite",
            ],
        },
        "tdd": {
            "typical_use": "承接 test_failed 后的 fix -> re-test 恢复链，适合需要验证收敛而不是只修一次的场景。",
            "template_names": [
                "template_fix_and_retest_after_test_failed",
            ],
        },
    }
    skills = [
        SkillCatalogItem(
            skill_name=skill.spec.name,
            description=skill.spec.description,
            skill_type=skill.spec.skill_type.value,
            capabilities=list(skill.spec.capabilities),
            enabled=skill.spec.enabled,
            typical_use=str(skill_catalog_hints.get(skill.spec.name, {}).get("typical_use", "")),
            template_names=[
                str(item)
                for item in skill_catalog_hints.get(skill.spec.name, {}).get("template_names", [])
                if str(item).strip()
            ],
        )
        for skill in skill_registry.list()
    ]
    return AgentCatalogResponse(
        total=len(agents),
        agents=agents,
        v2_agents=agents,
        v2_total=len(agents),
        v3_skills=skills,
        v3_total=len(skills),
    )


@router.get("/debug/usage/summary", response_model=UsageSummaryResponse, status_code=status.HTTP_200_OK)
def get_usage_summary(
    recent_limit: int = Query(default=20, ge=1, le=100, description="最近高消耗 run 返回数量。"),
) -> UsageSummaryResponse:
    """返回 token usage 聚合数据，供 Dashboard 展示。"""
    summary = get_v2_runtime().get_usage_summary_for_ui(recent_limit=recent_limit)
    return UsageSummaryResponse.model_validate(summary)


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


@router.get("/debug/runs/{run_id}/detail", response_model=RunDetailResponse, status_code=status.HTTP_200_OK)
def get_run_detail(run_id: str) -> RunDetailResponse:
    """按 run_id 查询统一详情视图，当前支持 v2 / v3 分流。"""
    db = SQLiteDB()
    row = db.fetchone(
        """
        SELECT run_id, session_id, model, task, workdir, status, step_count, final_output, created_at, updated_at,
               COALESCE(agent_version, 'v1') AS agent_version
        FROM runs
        WHERE run_id = ?
        """,
        (run_id,),
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"未找到 run_id={run_id}。")

    version = str(row["agent_version"] or "v1").strip().lower()
    if version == "v2":
        replay = get_v2_runtime().get_run_replay(run_id)
        if not replay or not replay.get("run"):
            raise HTTPException(status_code=404, detail=f"未找到 run_id={run_id} 的 v2 replay。")
        return RunDetailResponse(version="v2", **replay)

    run_data = dict(row)
    trace_events = [event.model_dump() for event in get_trace_repository().query_timeline(run_id)]
    detail = RunDetailResponse(
        version=version,
        run=run_data,
        trace=trace_events,
    )
    if version == "v3":
        graph_finished = next(
            (
                event
                for event in reversed(trace_events)
                if event.get("event_type") == "graph_finished" and isinstance(event.get("payload"), dict)
            ),
            None,
        )
        if graph_finished is not None:
            payload = dict(graph_finished["payload"])
            detail.report = payload
            shared_state = payload.get("shared_state")
            if isinstance(shared_state, dict):
                planning = shared_state.get("planning")
                if isinstance(planning, dict):
                    detail.planning = planning
            execution_nodes = payload.get("execution_nodes")
            if isinstance(execution_nodes, list):
                detail.execution_nodes = execution_nodes
            trigger_diagnostics = payload.get("trigger_diagnostics")
            if isinstance(trigger_diagnostics, list):
                detail.trigger_diagnostics = trigger_diagnostics
    return detail


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
    rag_id: str | None = Query(default=None, description="可选知识库标识；不传使用 default。"),
) -> RagOverviewResponse:
    """返回当前 Chroma 向量库概览，供 Web UI 展示。"""
    normalized_rag_id = _normalize_debug_rag_id(rag_id)
    vector_store = ChromaVectorStore()
    overview = vector_store.inspect(rag_id=normalized_rag_id)
    rag_config = RagConfigStore().get(normalized_rag_id)

    embedding_model = getattr(settings, "embedding_model", "") or "local-hash"
    embedding_api_key = getattr(settings, "embedding_api_key", "")
    embedding_base_url = getattr(settings, "embedding_base_url", settings.llm_base_url)
    embedding_provider = "openai-compatible" if embedding_model != "local-hash" and bool(embedding_api_key) else "local-hash"

    all_files = overview["files"]
    paged_files = all_files[offset : offset + limit]

    return RagOverviewResponse(
        backend="chroma",
        rag_id=overview["rag_id"],
        collection_name=overview["collection_name"],
        persist_dir=overview["persist_dir"],
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        embedding_base_url=embedding_base_url,
        chunk_size=rag_config.chunk_size,
        overlap=rag_config.overlap,
        total_chunks=overview["total_chunks"],
        file_count=overview["file_count"],
        limit=limit,
        offset=offset,
        sampled_chunk_count=overview["sampled_chunk_count"],
        files=[RagFileItem.model_validate(item) for item in paged_files],
    )


@router.get("/debug/rag/collections", response_model=RagCollectionsResponse, status_code=status.HTTP_200_OK)
def list_rag_collections() -> RagCollectionsResponse:
    """返回当前可用 RAG 集合列表（rag_id / collection_name）。"""
    vector_store = ChromaVectorStore()
    items = vector_store.list_rag_collections()
    if not any(item.get("rag_id") == "default" for item in items):
        items = [{"rag_id": "default", "collection_name": vector_store.default_collection_name}, *items]
    return RagCollectionsResponse(
        total=len(items),
        items=[RagCollectionItem.model_validate(item) for item in items],
    )


@router.post(
    "/debug/rag/collections",
    response_model=RagCreateCollectionResponse,
    status_code=status.HTTP_200_OK,
)
def create_rag_collection(request: RagCreateCollectionRequest) -> RagCreateCollectionResponse:
    """创建空 RAG 向量集合（若已存在则幂等）。便于在导入文档前先在 UI 中选库。"""
    raw = request.rag_id.strip()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rag_id 不能为空")
    try:
        normalized_rag_id = strict_normalize_v2_rag_tokens([raw])[0]
    except RagIdValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    vector_store = ChromaVectorStore()
    info = vector_store.ensure_rag_collection(normalized_rag_id)
    try:
        rag_config = RagConfigStore().save(
            RagIndexConfig(
                rag_id=normalized_rag_id,
                chunk_size=request.chunk_size,
                overlap=request.overlap,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RagCreateCollectionResponse(
        rag_id=str(info["rag_id"]),
        collection_name=str(info["collection_name"]),
        chunk_size=rag_config.chunk_size,
        overlap=rag_config.overlap,
    )


@router.delete(
    "/debug/rag/collections/{rag_id}",
    response_model=RagDeleteCollectionResponse,
    status_code=status.HTTP_200_OK,
)
def delete_rag_collection(rag_id: str) -> RagDeleteCollectionResponse:
    """删除非 default RAG 集合及其轻量配置。"""
    try:
        normalized_rag_id = strict_normalize_v2_rag_tokens([rag_id])[0]
    except RagIdValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if normalized_rag_id == "default":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="default 知识库不允许删除。")

    vector_store = ChromaVectorStore()
    try:
        info = vector_store.delete_rag_collection(normalized_rag_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    config_deleted = RagConfigStore().delete(normalized_rag_id)
    return RagDeleteCollectionResponse(
        rag_id=str(info["rag_id"]),
        collection_name=str(info["collection_name"]),
        config_deleted=config_deleted,
    )


@router.post("/debug/rag/delete-source", response_model=RagDeleteSourceResponse, status_code=status.HTTP_200_OK)
def delete_rag_source(request: RagDeleteSourceRequest) -> RagDeleteSourceResponse:
    """按 source 删除向量库中的文档分块。"""
    source = request.source.strip()
    if not source:
        raise HTTPException(status_code=400, detail="source 不能为空。")
    normalized_rag_id = _normalize_debug_rag_id(request.rag_id)
    vector_store = ChromaVectorStore()
    deleted_chunks = vector_store.delete_by_source(source, rag_id=normalized_rag_id)
    return RagDeleteSourceResponse(source=source, rag_id=normalized_rag_id, deleted_chunks=deleted_chunks)


@router.post("/debug/rag/reindex-source", response_model=RagReindexSourceResponse, status_code=status.HTTP_200_OK)
def reindex_rag_source(request: RagReindexSourceRequest) -> RagReindexSourceResponse:
    """按 source 删除旧分块后重建索引。"""
    source = request.source.strip()
    if not source:
        raise HTTPException(status_code=400, detail="source 不能为空。")

    normalized_rag_id = _normalize_debug_rag_id(request.rag_id)
    target_path = (BASE_DIR / source).resolve()
    base_dir_resolved = BASE_DIR.resolve()
    if base_dir_resolved not in target_path.parents:
        raise HTTPException(status_code=400, detail="source 非法，必须位于仓库目录内。")
    if not target_path.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {source}")

    vector_store = ChromaVectorStore()
    rag_config = RagConfigStore().get(normalized_rag_id)
    try:
        deleted_chunks = vector_store.delete_by_source(source, rag_id=normalized_rag_id)
        ingested_chunks = DocsIngestor(
            vector_store=vector_store,
            chunk_size=rag_config.chunk_size,
            overlap=rag_config.overlap,
        ).ingest_file(target_path, rag_id=normalized_rag_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return RagReindexSourceResponse(
        source=source,
        rag_id=normalized_rag_id,
        deleted_chunks=deleted_chunks,
        ingested_chunks=ingested_chunks,
    )


@router.post("/debug/rag/upload", response_model=RagUploadResponse, status_code=status.HTTP_200_OK)
def upload_rag_file(request: RagUploadRequest) -> RagUploadResponse:
    """上传文件并导入 Chroma。"""
    normalized_rag_id = _normalize_debug_rag_id(request.rag_id)
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
        rag_config = RagConfigStore().get(normalized_rag_id)
        ingested_chunks = DocsIngestor(
            chunk_size=rag_config.chunk_size,
            overlap=rag_config.overlap,
        ).ingest_file(target_path, rag_id=normalized_rag_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    source = str(target_path.relative_to(BASE_DIR.resolve()))
    return RagUploadResponse(source=source, rag_id=normalized_rag_id, ingested_chunks=ingested_chunks)
