"""规划器基础接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.contracts.planner import PlanStep


class Planner(ABC):
    """规划器抽象接口。"""

    @abstractmethod
    def should_plan(self, task: str) -> bool:
        """判断当前任务是否需要拆解。"""

    @abstractmethod
    def create_plan(self, task: str) -> list[PlanStep]:
        """将任务拆解为有序步骤列表。"""
