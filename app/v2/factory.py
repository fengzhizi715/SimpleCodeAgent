"""V2 默认组件装配。"""

from __future__ import annotations

from app.trace.repository import SQLiteTraceRepository
from app.v1.planner.simple_planner import SimplePlanner
from app.v1.runtime.loop import AgentLoop
from app.v2.agents import AnalystAgent, CoderAgent, PlannerAgent, ReviewerAgent, TesterAgent
from app.v2.context import ContextBuilder
from app.v2.registry import AgentRegistry
from app.v2.repository import V2Repository
from app.v2.runtime import OrchestratorRuntime


def build_default_registry() -> AgentRegistry:
    """构造默认 Agent Registry。

    当前仍是静态装配式注册：
    适合课程演示和边界清晰的 MVP，不等价于动态服务发现或插件市场。
    """
    registry = AgentRegistry()
    registry.register(PlannerAgent(SimplePlanner()))
    registry.register(AnalystAgent())
    registry.register(CoderAgent(AgentLoop()))
    registry.register(ReviewerAgent())
    registry.register(TesterAgent())
    return registry


def build_orchestrator_runtime(trace_repository: SQLiteTraceRepository) -> OrchestratorRuntime:
    """构造默认 V2 Orchestrator Runtime。"""
    return OrchestratorRuntime(
        registry=build_default_registry(),
        trace_repository=trace_repository,
        v2_repository=V2Repository(trace_repository.db),
        context_builder=ContextBuilder(),
    )
