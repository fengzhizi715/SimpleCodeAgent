"""Agent 运行接口。"""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import (
    get_agent_loop,
    get_planner,
    get_provider,
    get_session_memory,
    get_summary_memory,
    get_trace_repository,
)
from app.contracts.run import RunMetrics, RunUsage
from app.core.config import settings
from app.core.exceptions import AppError, UnsupportedAgentVersionError
from app.core.logger import get_logger, log_context
from app.llm.client import LLMProviderError
from app.v1.tools.registry import ToolRegistry

logger = get_logger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRunRequest(BaseModel):
    """Agent 运行请求。"""

    model_config = ConfigDict(extra="forbid")

    task: str = Field(min_length=1, description="要执行的任务描述。")
    version: Literal["v1", "v2"] = Field(default="v1", description="选择 Agent 版本。")
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
    run_timeout_seconds: int = Field(default=120, ge=1, le=3600, description="单次运行超时时间。")
    include_trace: bool = Field(default=False, description="是否在响应中附带简版 Trace。")


class AgentRunResponse(BaseModel):
    """Agent 运行响应。"""

    model_config = ConfigDict(extra="forbid")

    answer: str
    version: Literal["v1", "v2"]
    run_id: str
    session_id: str
    reasoning_mode: Literal["default", "low", "medium", "high"] = "default"
    status: str | None = None
    step_count: int = 0
    usage: RunUsage | None = None
    metrics: RunMetrics | None = None
    trace: list[dict[str, object]] = Field(default_factory=list)


@router.post("/run", response_model=AgentRunResponse, status_code=status.HTTP_200_OK)
def run_agent(request: AgentRunRequest) -> AgentRunResponse:
    """执行一次 Agent 任务。"""
    if request.version == "v2":
        raise HTTPException(status_code=501, detail="v2 API 入口已预留，但当前尚未实现。")
    if request.version != "v1":
        raise HTTPException(status_code=400, detail=f"不支持的 Agent 版本：{request.version}")
    resolved_model = request.model or settings.llm_model
    if not resolved_model:
        raise HTTPException(status_code=400, detail="缺少模型名，请在请求中传入 model 或配置 LLM_MODEL。")
    if not (request.api_key or request.service_token or settings.llm_api_key or settings.llm_service_token):
        raise HTTPException(
            status_code=400,
            detail="缺少鉴权信息，请传入 api_key / service_token，或配置 LLM_API_KEY / LLM_SERVICE_TOKEN。",
        )

    session_id = request.session_id or str(uuid4())
    resolved_workdir = request.workdir or request.project_root or settings.workdir or None

    with log_context(session_id=session_id):
        logger.info(
            "Received API run request: version=%s model=%s workdir=%s reasoning_mode=%s include_trace=%s",
            request.version,
            request.model or settings.llm_model or "<missing>",
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
            loop = get_agent_loop()
            planner = get_planner()
            session_memory = get_session_memory()
            summary_memory = get_summary_memory()
            tool_registry = ToolRegistry(workspace_root=resolved_workdir)
            tool_registry.register_default_tools()

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
