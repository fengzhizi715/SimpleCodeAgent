"""V3 graph-based skill runtime."""

from __future__ import annotations

from app.v3.contracts.skill_contracts import SkillSpec, SkillType
from app.v3.graph.graph_validator import GraphValidator
from app.v3.runtime.execution_kernel import ExecutionKernel
from app.v3.runtime.graph_executor import GraphExecutor
from app.v3.runtime.skill_executor import SkillExecutor
from app.v3.skills.builtin.coding_skill import CodingSkill
from app.v3.skills.builtin.planning_skill import PlanningSkill
from app.v3.skills.registry import SkillRegistry


def build_default_skill_registry() -> SkillRegistry:
    """Build the default V3 skill registry."""
    registry = SkillRegistry()
    registry.register(
        PlanningSkill(
            SkillSpec(
                name="planning",
                description="Generate a minimal task graph for a user goal.",
                skill_type=SkillType.COMPOSITE,
                capabilities=["graph.plan"],
            )
        )
    )
    registry.register(
        CodingSkill(
            SkillSpec(
                name="coding",
                description="Execute a minimal coding skill.",
                skill_type=SkillType.COMPOSITE,
                capabilities=["code.modify"],
            )
        )
    )
    return registry


def build_execution_kernel(registry: SkillRegistry | None = None) -> ExecutionKernel:
    """Build the default V3 execution kernel."""
    skill_registry = registry or build_default_skill_registry()
    skill_executor = SkillExecutor(skill_registry)
    graph_executor = GraphExecutor(skill_executor=skill_executor)
    return ExecutionKernel(
        graph_executor=graph_executor,
        validator=GraphValidator(),
    )


__all__ = [
    "ExecutionKernel",
    "GraphExecutor",
    "GraphValidator",
    "SkillExecutor",
    "SkillRegistry",
    "build_default_skill_registry",
    "build_execution_kernel",
]
