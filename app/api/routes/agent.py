"""Agent 运行接口。"""

from __future__ import annotations

import asyncio
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.deps import (
    get_agent_loop,
    get_memory_repository,
    get_planner,
    get_provider,
    get_session_memory,
    get_summary_memory,
    get_trace_repository,
    get_v2_runtime,
    get_trigger_hit_counter,
    get_trigger_rule_state_store,
)
from app.contracts.run import RunMetrics, RunUsage
from app.core.config import settings
from app.core.config import get_effective_llm_model
from app.core.exceptions import AppError, RagIdValidationError, UnsupportedAgentVersionError
from app.core.logger import get_logger, log_context
from app.core.session import derive_project_session_id
from app.llm.client import LLMProviderError
from app.v1.tools.registry import ToolRegistry
from app.v3.contracts.execution_contracts import ExecutionReport
from app.v3.contracts.graph_contracts import GraphInspection, TaskGraph
from app.v3.contracts.planning_contracts import PlanningResult
from app.v3.runner import inspect_v3_graph, plan_v3_graph, run_v3
from app.v3.runtime.skill_executor import SkillExecutor
from app.v3 import build_default_skill_registry

logger = get_logger(__name__)

router = APIRouter(tags=["agent"])


class V2ReviewStrategyRequest(BaseModel):
    """V2 Reviewer 运行级策略配置。"""

    model_config = ConfigDict(extra="forbid")

    llm_enabled: bool = Field(default=True, description="是否启用 LLM review。")
    strictness: Literal["light", "normal", "strict"] = Field(default="normal", description="规则严格度。")
    max_issues: int = Field(default=5, ge=1, le=10, description="LLM review 最多返回的问题数。")
    focus_areas: list[str] = Field(default_factory=list, max_length=8, description="LLM review 重点关注方向。")
    rule_groups: list[
        Literal["scope", "testing", "security", "maintainability", "boundaries", "api", "domain"]
    ] = Field(
        default_factory=lambda: ["scope", "testing", "security", "maintainability", "boundaries", "api", "domain"],
        description="启用的规则分组。",
    )
    test_failure_mode: Literal["off", "suggest", "block"] = Field(
        default="block",
        description="Reviewer 对最新测试失败结果的联动策略。",
    )


class V2ExternalCodingRequest(BaseModel):
    """V2 外部编码执行器运行级配置。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="是否允许 Planner 规划 external coding step。")
    preferred_agent: Literal["codex_cli", "cursor_cli"] = Field(
        default="codex_cli",
        description="优先使用的外部 Coding CLI。",
    )
    allow_raw_external_command: bool = Field(
        default=False,
        description="是否允许 Planner 直接下发 external_command（默认关闭，优先模板构建）。",
    )
    codex_template: str = Field(
        default="codex exec --sandbox workspace-write {prompt}",
        description="codex_cli 命令模板（外部编码需 workspace-write 才能落盘）；支持 {prompt} 和 {workdir} 占位符。",
    )
    cursor_template: str = Field(
        default="cursor-agent --trust {prompt}",
        description="cursor_cli 命令模板（默认可执行文件为 cursor-agent，后端非交互运行需 --trust）；支持 {prompt} 和 {workdir}。",
    )
    cursor_cli_path: str | None = Field(
        default=None,
        description="Cursor CLI 可执行文件绝对路径；与环境变量 CURSOR_CLI_PATH 等价，可解决 uvicorn PATH 中找不到 cursor。",
    )
    codex_cli_path: str | None = Field(
        default=None,
        description="Codex CLI 可执行文件绝对路径；与环境变量 CODEX_CLI_PATH 等价。",
    )

    @field_validator("cursor_cli_path", "codex_cli_path", mode="before")
    @classmethod
    def _blank_cli_paths_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class AgentRunRequest(BaseModel):
    """Agent 运行请求。"""

    model_config = ConfigDict(extra="forbid")

    task: str | None = Field(default=None, description="要执行的任务描述。v3 下会作为 goal 使用。")
    version: Literal["v1", "v2", "v3"] = Field(default="v1", description="选择 Agent 版本。")
    session_id: str | None = Field(default=None, description="可选会话 ID。")
    workdir: str | None = Field(
        default=None,
        description="目标工作目录。未传时默认使用当前仓库或 WORKDIR。",
    )
    project_root: str | None = Field(
        default=None,
        description="历史兼容字段，等价于 workdir。优先使用 workdir。",
    )
    model: str | None = Field(default=None, description="可覆盖的模型名。")
    reasoning_mode: Literal["default", "low", "medium", "high"] = Field(
        default="default",
        description="运行时的 reasoning 模式标记。",
    )
    base_url: str | None = Field(default=None, description="可覆盖的 LLM Base URL。")
    api_key: str | None = Field(default=None, description="可覆盖的 LLM API Key。")
    service_token: str | None = Field(default=None, description="可覆盖的 Service Token。")
    system_prompt: str = Field(default="You are a helpful assistant.", description="系统提示词。")
    temperature: float = Field(default=0.0, description="采样温度。")
    max_steps: int = Field(default=3, ge=1, le=20, description="最大执行步数。")
    run_timeout_seconds: int = Field(default=120, ge=1, le=1800, description="单次运行超时时间。")
    include_trace: bool = Field(default=False, description="是否在响应中附带简版 Trace。")
    include_events: bool = Field(default=True, description="v3 是否在响应中附带本地事件记录。")
    autonomy_enabled: bool = Field(default=False, description="v3 是否启用受控自治 follow-up 能力。")
    plan_only: bool = Field(default=False, description="v3 是否只返回 planning/inspection，不执行 graph。")
    graph: TaskGraph | None = Field(default=None, description="v3 可选显式 graph。")
    v3_coding_execution_mode: Literal["internal", "external"] = Field(
        default="internal",
        description="v3 coding skill 的执行后端；internal 走内置 coder，external 走外部 CLI coder。",
    )
    v2_enabled_agents: list[
        Literal["orchestrator", "planner", "analyst", "coder", "external_coder", "tester", "reviewer"]
    ] | None = Field(
        default=None,
        description="V2 可视化运行级 Agent 配置；orchestrator / planner 会始终启用。",
    )
    v2_review_strategy: V2ReviewStrategyRequest | None = Field(
        default=None,
        description="V2 Reviewer 运行级策略；仅在启用 reviewer 时生效。",
    )
    v2_use_rag: bool = Field(default=True, description="V2 是否允许本次运行使用 RAG 检索。")
    rag_id: str | None = Field(
        default=None,
        description="可选知识库标识；v2 模式下用于路由 retrieve_docs 到指定 RAG。",
    )
    rag_ids: list[str] | None = Field(
        default=None,
        description="可选知识库标识列表；v2 模式下用于多库并查。",
    )
    v2_external_coding: V2ExternalCodingRequest | None = Field(
        default=None,
        description="V2 外部编码执行器配置（Codex/Cursor CLI）。",
    )

    @model_validator(mode="after")
    def _validate_task_requirements(self) -> "AgentRunRequest":
        if self.version in {"v1", "v2"} and not str(self.task or "").strip():
            raise ValueError("v1/v2 请求必须提供 task。")
        if self.version == "v3" and not (str(self.task or "").strip() or self.graph is not None):
            raise ValueError("v3 请求必须提供 task(goal) 或 graph。")
        return self


class AgentRunResponse(BaseModel):
    """Agent 运行响应。"""

    model_config = ConfigDict(extra="forbid")

    answer: str
    version: Literal["v1", "v2", "v3"]
    run_id: str
    session_id: str
    reasoning_mode: Literal["default", "low", "medium", "high"] = "default"
    status: str | None = None
    step_count: int = 0
    usage: RunUsage | None = None
    metrics: RunMetrics | None = None
    trace: list[dict[str, object]] = Field(default_factory=list)
    report: ExecutionReport | None = None
    planning: PlanningResult | None = None
    inspection: GraphInspection | None = None
    autonomy: dict[str, object] | None = None
    events: list[dict[str, object]] = Field(default_factory=list)


class AgentPlanRequest(BaseModel):
    """统一 planning 请求；当前由 v3 提供结构化 graph planning。"""

    model_config = ConfigDict(extra="forbid")

    version: Literal["v3"] = Field(default="v3", description="当前仅支持 v3 planning。")
    task: str | None = Field(
        default=None,
        description="与 /run 的 task 同义；在 v3 中作为 planning goal 使用。",
    )
    goal: str | None = Field(
        default=None,
        description="兼容字段，等价于 task；优先推荐使用 task。",
    )
    workdir: str | None = Field(default=None, description="可选 workspace root。")
    project_root: str | None = Field(default=None, description="历史兼容字段，等价于 workdir。")
    rag_id: str | None = Field(default=None, description="可选知识库标识；v3 检索节点会使用它。")
    rag_ids: list[str] | None = Field(default=None, description="可选知识库标识列表；v3 检索节点支持多库并查。")
    v3_coding_execution_mode: Literal["internal", "external"] = Field(
        default="internal",
        description="v3 coding skill 的执行后端。",
    )
    v3_external_coding: V2ExternalCodingRequest | None = Field(
        default=None,
        description="v3 external coding 配置；仅在 v3_coding_execution_mode=external 时生效。",
    )

    @model_validator(mode="after")
    def _normalize_goal_alias(self) -> "AgentPlanRequest":
        resolved_task = str(self.task or self.goal or "").strip()
        if not resolved_task:
            raise ValueError("planning 请求必须提供 task（或兼容字段 goal）。")
        self.task = resolved_task
        if self.goal is not None:
            self.goal = str(self.goal).strip() or None
        return self


class AgentPlanResponse(BaseModel):
    """统一 planning 响应。"""

    model_config = ConfigDict(extra="forbid")

    version: Literal["v3"] = "v3"
    planning: PlanningResult


class AgentInspectGraphRequest(BaseModel):
    """统一 graph inspection 请求；当前由 v3 提供 DAG inspection。"""

    model_config = ConfigDict(extra="forbid")

    version: Literal["v3"] = Field(default="v3", description="当前仅支持 v3 graph inspection。")
    task: str | None = Field(
        default=None,
        description="与 /run 的 task 同义；在 v3 中作为 planning goal 使用，可用于先生成 graph 再检查。",
    )
    goal: str | None = Field(
        default=None,
        description="兼容字段，等价于 task；优先推荐使用 task。",
    )
    graph: TaskGraph | None = Field(default=None, description="可选显式 graph。")
    workdir: str | None = Field(default=None, description="可选 workspace root。")
    project_root: str | None = Field(default=None, description="历史兼容字段，等价于 workdir。")
    rag_id: str | None = Field(default=None, description="可选知识库标识；v3 检索节点会使用它。")
    rag_ids: list[str] | None = Field(default=None, description="可选知识库标识列表；v3 检索节点支持多库并查。")
    v3_coding_execution_mode: Literal["internal", "external"] = Field(
        default="internal",
        description="v3 coding skill 的执行后端。",
    )
    v3_external_coding: V2ExternalCodingRequest | None = Field(
        default=None,
        description="v3 external coding 配置；仅在 v3_coding_execution_mode=external 时生效。",
    )

    @model_validator(mode="after")
    def _normalize_goal_alias(self) -> "AgentInspectGraphRequest":
        resolved_task = str(self.task or self.goal or "").strip() or None
        if resolved_task is None and self.graph is None:
            raise ValueError("graph inspection 请求必须提供 task（或兼容字段 goal）或 graph。")
        self.task = resolved_task
        if self.goal is not None:
            self.goal = str(self.goal).strip() or None
        return self


class AgentInspectGraphResponse(BaseModel):
    """统一 graph inspection 响应。"""

    model_config = ConfigDict(extra="forbid")

    version: Literal["v3"] = "v3"
    inspection: GraphInspection
    planning: PlanningResult | None = None


def _run_agent_impl(request: AgentRunRequest) -> AgentRunResponse:
    """执行一次 Agent 任务。"""
    if request.version not in {"v1", "v2", "v3"}:
        raise HTTPException(status_code=400, detail=f"不支持的 Agent 版本：{request.version}")
    if request.version == "v3":
        session_id = request.session_id or str(uuid4())
        resolved_workdir = request.workdir or request.project_root or settings.workdir or None
        hit_counter = get_trigger_hit_counter()
        trigger_rule_state_store = get_trigger_rule_state_store()
        try:
            result = asyncio.run(
                run_v3(
                    goal=request.task,
                    graph=request.graph,
                    workdir=resolved_workdir,
                    session_id=session_id,
                    model=request.model,
                    rag_id=request.rag_id,
                    rag_ids=request.rag_ids,
                    coding_execution_mode=request.v3_coding_execution_mode,
                    external_coding=(
                        request.v2_external_coding.model_dump()
                        if request.v3_coding_execution_mode == "external" and request.v2_external_coding is not None
                        else None
                    ),
                    autonomy_enabled=request.autonomy_enabled,
                    plan_only=request.plan_only,
                    include_events=request.include_events,
                    include_trace=request.include_trace,
                    hit_callback=hit_counter.increment,
                    trigger_rule_enabled_overrides=trigger_rule_state_store.get_all(),
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        report = result.get("report")
        planning = result.get("planning")
        inspection = result.get("inspection")
        run_id = (
            report.run_id
            if report is not None
            else (planning.graph.run_id if planning is not None else "")
        )
        status_value = report.status.value if report is not None else ("planned" if planning is not None else None)
        step_count = len(report.execution_nodes) if report is not None else (len(planning.graph.nodes) if planning is not None else 0)
        answer = report.model_dump_json(indent=2) if report is not None else "plan_only=true"
        return AgentRunResponse(
            answer=answer,
            version="v3",
            run_id=run_id,
            session_id=session_id,
            reasoning_mode=request.reasoning_mode,
            status=status_value,
            step_count=step_count,
            trace=result.get("trace", []),
            report=report,
            planning=planning,
            inspection=inspection,
            autonomy=result.get("autonomy"),
            events=result.get("events", []),
        )
    if request.version == "v1":
        rag_id = str(request.rag_id or "").strip()
        rag_ids = [str(item).strip() for item in (request.rag_ids or []) if str(item).strip()]
        if rag_ids:
            raise HTTPException(
                status_code=400,
                detail="v1 不支持多向量库参数 rag_ids；请使用 v2。",
            )
        if rag_id and rag_id != "default":
            raise HTTPException(
                status_code=400,
                detail="v1 仅支持默认向量库（default）；请使用 v2 访问自定义 rag_id。",
            )
    resolved_model = request.model or get_effective_llm_model()
    if not resolved_model:
        raise HTTPException(status_code=400, detail="缺少模型名，请在请求中传入 model 或配置 LLM_MODEL。")
    if not (request.api_key or request.service_token or settings.llm_api_key or settings.llm_service_token):
        raise HTTPException(
            status_code=400,
            detail="缺少鉴权信息，请传入 api_key / service_token，或配置 LLM_API_KEY / LLM_SERVICE_TOKEN。",
        )

    resolved_workdir = request.workdir or request.project_root or settings.workdir or None
    session_id = request.session_id or str(uuid4())
    session_id = derive_project_session_id(session_id, resolved_workdir)

    with log_context(session_id=session_id):
        logger.info(
            "Received API run request: version=%s model=%s workdir=%s reasoning_mode=%s include_trace=%s",
            request.version,
            resolved_model or "<missing>",
            resolved_workdir or "<current-repo>",
            request.reasoning_mode,
            request.include_trace,
        )
        try:
            # Provider、memory、planner 仍然是共享底座；
            # 具体工具工作区则允许按请求覆盖，便于分析其他本地项目。
            provider = get_provider(
                base_url=request.base_url,
                api_key=request.api_key,
                service_token=request.service_token,
                model=request.model,
            )
            tool_registry = ToolRegistry(workspace_root=resolved_workdir)
            tool_registry.register_default_tools(multi_rag=(request.version == "v2" and request.v2_use_rag))
            if request.version == "v2":
                runtime = get_v2_runtime()
                try:
                    result = runtime.run(
                        provider=provider,
                        model=resolved_model,
                        task=request.task,
                        session_id=session_id,
                        tool_registry=tool_registry,
                        workspace_root=resolved_workdir or settings.workdir or ".",
                        reasoning_mode=request.reasoning_mode,
                        max_steps=request.max_steps,
                        run_timeout_seconds=request.run_timeout_seconds,
                        enabled_agents=request.v2_enabled_agents,
                        review_strategy=(
                            request.v2_review_strategy.model_dump()
                            if request.v2_review_strategy is not None
                            else None
                        ),
                        use_rag=request.v2_use_rag,
                        rag_id=request.rag_id if request.v2_use_rag else None,
                        rag_ids=request.rag_ids if request.v2_use_rag else None,
                        external_coding=(
                            request.v2_external_coding.model_dump()
                            if request.v2_external_coding is not None
                            else None
                        ),
                    )
                except RagIdValidationError as exc:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
            else:
                loop = get_agent_loop()
                planner = get_planner()
                session_memory = get_session_memory()
                summary_memory = get_summary_memory()

                # v1 仍然保留“简单任务直接执行，复杂任务先规划”的双路径。
                if planner.should_plan(request.task):
                    result = loop.run_with_plan(
                        provider=provider,
                        model=resolved_model,
                        task=request.task,
                        system_prompt=request.system_prompt,
                        session_id=session_id,
                        reasoning_mode=request.reasoning_mode,
                        temperature=request.temperature,
                        max_steps=request.max_steps,
                        run_timeout_seconds=request.run_timeout_seconds,
                        tool_registry=tool_registry,
                        session_memory=session_memory,
                        summary_memory=summary_memory,
                        planner=planner,
                    )
                else:
                    result = loop.run(
                        provider=provider,
                        model=resolved_model,
                        task=request.task,
                        system_prompt=request.system_prompt,
                        session_id=session_id,
                        reasoning_mode=request.reasoning_mode,
                        temperature=request.temperature,
                        max_steps=request.max_steps,
                        run_timeout_seconds=request.run_timeout_seconds,
                        tool_registry=tool_registry,
                        session_memory=session_memory,
                        summary_memory=summary_memory,
                    )
        except UnsupportedAgentVersionError as exc:
            logger.error("Unsupported agent version in API request: %s", exc)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (AppError, LLMProviderError) as exc:
            logger.exception("API agent run failed: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        # v1 规划路径会在子步骤中多次 save_run，task 可能为步骤/摘要提示词；这里用用户原始 task 再落库一次，
        # 确保历史列表与 Web UI 展示的 run_id 一致且摘要列可读。
        if request.version == "v1" and result.run_id and result.session_id:
            get_memory_repository().save_run(
                result,
                request.task,
                workdir=resolved_workdir,
                is_top_level=True,
                parent_run_id=None,
            )

        trace: list[dict[str, object]] = []
        if request.include_trace and result.run_id:
            trace = [
                event.model_dump()
                for event in get_trace_repository().query_timeline(result.run_id)
            ]

        logger.info(
            "Completed API run request: status=%s step_count=%s run_id=%s",
            result.status,
            result.step_count,
            result.run_id or "",
        )
        return AgentRunResponse(
            answer=result.final_output,
            version=request.version,
            run_id=result.run_id or "",
            session_id=result.session_id or session_id,
            reasoning_mode=result.reasoning_mode,
            status=result.status,
            step_count=result.step_count,
            usage=result.usage,
            metrics=result.metrics,
            trace=trace,
        )


@router.post("/run", response_model=AgentRunResponse, status_code=status.HTTP_200_OK)
def run_agent(request: AgentRunRequest) -> AgentRunResponse:
    """统一执行一次 Agent 任务。"""
    return _run_agent_impl(request)


@router.post("/agent/run", response_model=AgentRunResponse, status_code=status.HTTP_200_OK, include_in_schema=False)
def run_agent_legacy(request: AgentRunRequest) -> AgentRunResponse:
    """兼容旧的 /agent/run 路径。"""
    return _run_agent_impl(request)


@router.post("/plan", response_model=AgentPlanResponse, status_code=status.HTTP_200_OK)
async def plan_agent(request: AgentPlanRequest) -> AgentPlanResponse:
    """生成结构化计划；当前由 v3 planning 提供。"""
    resolved_workdir = request.workdir or request.project_root or "."
    try:
        planning = await plan_v3_graph(
            goal=request.task,
            workdir=resolved_workdir,
            skill_executor=SkillExecutor(
                build_default_skill_registry(workspace_root=resolved_workdir)
            ),
            rag_id=request.rag_id,
            rag_ids=request.rag_ids,
            coding_execution_mode=request.v3_coding_execution_mode,
            external_coding=(
                request.v3_external_coding.model_dump()
                if request.v3_coding_execution_mode == "external" and request.v3_external_coding is not None
                else None
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AgentPlanResponse(planning=planning)


@router.post("/inspect-graph", response_model=AgentInspectGraphResponse, status_code=status.HTTP_200_OK)
async def inspect_agent_graph(request: AgentInspectGraphRequest) -> AgentInspectGraphResponse:
    """检查 graph 结构；当前由 v3 graph inspection 提供。"""
    resolved_workdir = request.workdir or request.project_root
    try:
        inspection, planning = await inspect_v3_graph(
            goal=request.task,
            graph=request.graph,
            workdir=resolved_workdir,
            rag_id=request.rag_id,
            rag_ids=request.rag_ids,
            coding_execution_mode=request.v3_coding_execution_mode,
            external_coding=(
                request.v3_external_coding.model_dump()
                if request.v3_coding_execution_mode == "external" and request.v3_external_coding is not None
                else None
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AgentInspectGraphResponse(
        inspection=inspection,
        planning=planning,
    )
