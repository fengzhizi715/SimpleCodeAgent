"""Concrete V2 agent implementations."""

from typing import TypeAlias

from app.v2.base import AgentBase
from app.v2.agent_impls.analyst import AnalystAgent
from app.v2.agent_impls.coder import CoderAgent
from app.v2.agent_impls.orchestrator import OrchestratorAgent
from app.v2.agent_impls.planner import PlannerAgent
from app.v2.agent_impls.reviewer import ReviewerAgent
from app.v2.agent_impls.tester import TesterAgent

AgentClass: TypeAlias = type[AgentBase]

AGENT_CLASS_MAP: dict[str, AgentClass] = {
    "orchestrator": OrchestratorAgent,
    "planner": PlannerAgent,
    "analyst": AnalystAgent,
    "coder": CoderAgent,
    "tester": TesterAgent,
    "reviewer": ReviewerAgent,
}


def describe_agent_matrix() -> list[dict[str, object]]:
    """Return a stable role matrix for teaching/debug display."""
    matrix: list[dict[str, object]] = []
    for role in sorted(AGENT_CLASS_MAP):
        cls = AGENT_CLASS_MAP[role]
        instance = cls()  # type: ignore[call-arg]
        matrix.append(
            {
                "agent_id": instance.spec.agent_id,
                "role": instance.spec.role,
                "class_name": cls.__name__,
                "capabilities": list(instance.spec.capabilities),
                "availability": instance.spec.availability,
            }
        )
    return matrix


__all__ = [
    "AnalystAgent",
    "CoderAgent",
    "OrchestratorAgent",
    "PlannerAgent",
    "ReviewerAgent",
    "TesterAgent",
    "AGENT_CLASS_MAP",
    "describe_agent_matrix",
]
