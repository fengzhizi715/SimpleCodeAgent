"""V3 graph-based skill runtime."""

from __future__ import annotations

from pathlib import Path

from app.v3.adapters.v1_tool_adapter import V1ToolAdapter
from app.v3.adapters.v2_agent_adapter import V2AgentAdapter
from app.v3.contracts.skill_contracts import SkillSpec, SkillType
from app.v3.graph.graph_validator import GraphValidator
from app.v3.runtime.execution_kernel import ExecutionKernel
from app.v3.runtime.graph_executor import GraphExecutor
from app.v3.runtime.skill_executor import SkillExecutor
from app.v3.skills.builtin.coding_skill import CodingSkill
from app.v3.skills.builtin.planning_skill import PlanningSkill
from app.v3.skills.builtin.repo_analysis_skill import RepoAnalysisSkill
from app.v3.skills.builtin.retrieve_docs_skill import RetrieveDocsSkill
from app.v3.skills.builtin.tdd_skill import TDDSkill
from app.v3.skills.builtin.test_runner_skill import TestRunnerSkill
from app.v3.skills.registry import SkillRegistry


def build_default_skill_registry(workspace_root: str | Path | None = None) -> SkillRegistry:
    """Build the default V3 skill registry."""
    registry = SkillRegistry()
    registry.register(
        PlanningSkill(
            SkillSpec(
                name="planning",
                description="Generate a minimal task graph for a user goal.",
                skill_type=SkillType.COMPOSITE,
                capabilities=["graph.plan"],
                emits_events=[],
                typical_use="根据任务目标、仓库特征和 RAG 配置，生成适合当前场景的 graph 模板与恢复策略。",
                template_names=[
                    "analysis_only",
                    "analysis_with_context",
                    "testing_branch_verify",
                    "coding_focus_then_full_suite",
                    "default",
                ],
            )
        )
    )
    registry.register(
        RetrieveDocsSkill(
            SkillSpec(
                name="retrieve_docs",
                description="Retrieve external documentation context for the current goal.",
                skill_type=SkillType.TOOL,
                capabilities=["docs.retrieve", "rag.query"],
                timeout_seconds=60,
                typical_use="在分析或改码前补充外部文档、知识库或多 RAG 检索上下文。",
                template_names=[
                    "analysis_with_context",
                    "default",
                ],
            ),
            docs_adapter=V1ToolAdapter.for_retrieve_docs(workspace_root=workspace_root, allow_multi_rag=True),
        )
    )
    registry.register(
        RepoAnalysisSkill(
            SkillSpec(
                name="analyze_repo",
                description="Inspect the repository and expose a lightweight profile.",
                skill_type=SkillType.COMPOSITE,
                capabilities=["repo.inspect"],
                emits_events=[],
                typical_use="抽取仓库画像、候选测试命令和测试目标，为后续 coding / testing 节点提供上下文。",
                template_names=[
                    "analysis_only",
                    "analysis_with_context",
                    "testing_branch_verify",
                    "coding_focus_then_full_suite",
                    "default",
                ],
            )
        )
    )
    registry.register(
        CodingSkill(
            SkillSpec(
                name="coding",
                description="Execute coding through an internal or external backend.",
                skill_type=SkillType.COMPOSITE,
                capabilities=["code.modify"],
                emits_events=["code_updated"],
                retryable=True,
                timeout_seconds=300,
                typical_use="执行真实改码动作，可切换 internal / external 后端，并承接 test_failed 之后的 fix-only 恢复。",
                template_names=[
                    "default",
                    "coding_focus_then_full_suite",
                    "template_fix_after_test_failed",
                ],
            ),
            internal_agent_adapter=V2AgentAdapter.for_coder(workspace_root=workspace_root),
            external_agent_adapter=V2AgentAdapter.for_external_coder(workspace_root=workspace_root),
        )
    )
    registry.register(
        TestRunnerSkill(
            SkillSpec(
                name="test_runner",
                description="Run a controlled verification command.",
                skill_type=SkillType.TOOL,
                capabilities=["test.run"],
                emits_events=["test_started", "test_passed", "test_failed"],
                retryable=True,
                timeout_seconds=60,
                typical_use="执行 focused test 或 full-suite verification，既能作为主链节点，也能作为恢复后的验证节点。",
                template_names=[
                    "default",
                    "testing_branch_verify",
                    "coding_focus_then_full_suite",
                ],
            ),
            shell_adapter=V1ToolAdapter.for_shell_run(workspace_root=workspace_root),
        )
    )
    skill_executor = SkillExecutor(registry)
    registry.register(
        TDDSkill(
            SkillSpec(
                name="tdd",
                description="Run a tiny fix-and-retest recovery loop.",
                skill_type=SkillType.COMPOSITE,
                capabilities=["code.recover", "test.retry"],
                consumes_events=["test_failed"],
                emits_events=["code_updated", "test_passed", "test_failed"],
                retryable=True,
                timeout_seconds=300,
                typical_use="承接 test_failed 后的 fix -> re-test 恢复链，适合需要验证收敛而不是只修一次的场景。",
                template_names=[
                    "template_fix_and_retest_after_test_failed",
                ],
            ),
            skill_executor=skill_executor,
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
