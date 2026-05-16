"""API 依赖注入。"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import (
    get_effective_llm_base_url,
    get_effective_llm_model,
    settings,
)
from app.core.logger import get_logger
from app.llm.client import OpenAICompatibleProvider
from app.trace.repository import SQLiteTraceRepository
from app.v1.memory.repository import SQLiteMemoryRepository
from app.v1.memory.session_memory import SessionMemory
from app.v1.memory.summary_memory import SummaryMemory
from app.v1.planner.simple_planner import SimplePlanner
from app.v1.runtime.loop import AgentLoop
from app.v2.factory import build_orchestrator_runtime
from app.v2.runtime import OrchestratorRuntime
from app.api.trigger_state_store import TriggerRuleStateStore
from app.api.trigger_hit_counter import TriggerHitCounter

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_memory_repository() -> SQLiteMemoryRepository:
    """返回共享的 SQLite Memory 仓储。"""
    return SQLiteMemoryRepository()


@lru_cache(maxsize=1)
def get_agent_loop() -> AgentLoop:
    """返回共享的 AgentLoop。"""
    return AgentLoop()


@lru_cache(maxsize=1)
def get_v2_runtime() -> OrchestratorRuntime:
    """返回共享的 V2 Orchestrator Runtime。"""
    return build_orchestrator_runtime(get_trace_repository())


@lru_cache(maxsize=1)
def get_planner() -> SimplePlanner:
    """返回共享的简单规划器。"""
    return SimplePlanner()


def get_session_memory() -> SessionMemory:
    """构造会话记忆对象。"""
    return SessionMemory(get_memory_repository())


def get_summary_memory() -> SummaryMemory:
    """构造摘要记忆对象。"""
    return SummaryMemory(get_memory_repository())


def get_trace_repository() -> SQLiteTraceRepository:
    """构造 Trace 仓储。"""
    return SQLiteTraceRepository(get_memory_repository().db)


def get_provider(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    service_token: str | None = None,
    model: str | None = None,
) -> OpenAICompatibleProvider:
    """按请求参数构造 Provider。"""
    resolved_base_url = base_url or get_effective_llm_base_url()
    resolved_api_key = api_key or settings.llm_api_key
    resolved_service_token = service_token or settings.llm_service_token
    resolved_model = model or get_effective_llm_model()
    logger.info(
        "Building provider: base_url=%s model=%s auth_mode=%s has_api_key=%s has_service_token=%s",
        resolved_base_url,
        resolved_model,
        settings.llm_auth_mode,
        bool(resolved_api_key),
        bool(resolved_service_token),
    )
    return OpenAICompatibleProvider(
        base_url=resolved_base_url,
        api_key=resolved_api_key,
        service_token=resolved_service_token,
        auth_mode=settings.llm_auth_mode,
        reasoning_param_style=settings.llm_reasoning_param_style,
        model=resolved_model,
        timeout=settings.llm_timeout,
    )


@lru_cache(maxsize=1)
def get_trigger_rule_state_store() -> TriggerRuleStateStore:
    """返回共享的 Trigger Rule 状态存储。"""
    return TriggerRuleStateStore()


@lru_cache(maxsize=1)
def get_trigger_hit_counter() -> TriggerHitCounter:
    """返回共享的 Trigger Hit 计数器。"""
    return TriggerHitCounter()
