"""V2 Agent Registry。"""

from __future__ import annotations

from app.contracts.agent import AgentSpec
from app.v2.base import AgentBase


class AgentRegistry:
    """统一管理可用 Agent。"""

    def __init__(self) -> None:
        self._agents: dict[str, AgentBase] = {}

    def register(self, agent: AgentBase) -> None:
        """注册 Agent。"""
        self._agents[agent.spec.agent_id] = agent

    def get(self, agent_id: str) -> AgentBase | None:
        """按 agent_id 获取 Agent。"""
        return self._agents.get(agent_id)

    def list_specs(self) -> list[AgentSpec]:
        """列出全部 Agent 定义。"""
        return [agent.spec for agent in self._agents.values()]

    def list_available(self) -> list[AgentSpec]:
        """列出当前可用 Agent。"""
        return [spec for spec in self.list_specs() if spec.availability == "enabled"]
