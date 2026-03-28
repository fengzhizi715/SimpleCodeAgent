"""API 依赖注入。"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.llm.client import OpenAICompatibleProvider
from app.trace.repository import SQLiteTraceRepository
from app.v1.memory.repository import SQLiteMemoryRepository
from app.v1.memory.session_memory import SessionMemory
from app.v1.memory.summary_memory import SummaryMemory
from app.v1.planner.simple_planner import SimplePlanner
from app.v1.runtime.loop import AgentLoop
from app.v1.tools.registry import ToolRegistry


@lru_cache(maxsize=1)
def get_memory_repository() -> SQLiteMemoryRepository:
    """返回共享的 SQLite Memory 仓储。"""
    return SQLiteMemoryRepository()


@lru_cache(maxsize=1)
def get_tool_registry() -> ToolRegistry:
    """返回默认工具注册表。"""
    registry = ToolRegistry()
    registry.register_default_tools()
    return registry


@lru_cache(maxsize=1)
def get_agent_loop() -> AgentLoop:
    """返回共享的 AgentLoop。"""
    return AgentLoop()


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
    resolved_base_url = base_url or settings.llm_base_url
    resolved_api_key = api_key or settings.llm_api_key
    resolved_service_token = service_token or settings.llm_service_token
    resolved_model = model or settings.llm_model
    return OpenAICompatibleProvider(
        base_url=resolved_base_url,
        api_key=resolved_api_key,
        service_token=resolved_service_token,
        auth_mode=settings.llm_auth_mode,
        model=resolved_model,
        timeout=settings.llm_timeout,
    )
