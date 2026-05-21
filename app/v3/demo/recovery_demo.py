"""Stable recovery demo runner for V3 P1 productization."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Literal

from app.v3.adapters.v1_tool_adapter import V1ToolAdapter
from app.v3.contracts.skill_contracts import SkillInput, SkillOutput, SkillSpec, SkillType
from app.v3.runner import run_v3
from app.v3.runtime.skill_executor import SkillExecutor
from app.v3.skills.base import Skill
from app.v3.skills.builtin.planning_skill import PlanningSkill
from app.v3.skills.builtin.repo_analysis_skill import RepoAnalysisSkill
from app.v3.skills.builtin.tdd_skill import TDDSkill
from app.v3.skills.builtin.test_runner_skill import TestRunnerSkill
from app.v3.skills.registry import SkillRegistry


RecoveryDemoScenario = Literal["success", "no_code_changes"]


def _build_recovery_demo_workspace() -> Path:
    root = Path(tempfile.mkdtemp(prefix="v3-recovery-demo-"))
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "calc.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a - b\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_calc.py").write_text(
        (
            "import sys\n"
            "from pathlib import Path\n\n"
            "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
            "from calc import add\n\n\n"
            "def test_add() -> None:\n"
            "    assert add(2, 3) == 5\n"
        ),
        encoding="utf-8",
    )
    return root


class DemoRecoveryCodingSkill(Skill):
    """Deterministic coding skill used only by the P1 recovery demo."""

    def __init__(self, *, workspace_root: Path, scenario: RecoveryDemoScenario) -> None:
        super().__init__(
            SkillSpec(
                name="coding",
                description="deterministic recovery demo coder",
                skill_type=SkillType.COMPOSITE,
                capabilities=["code.modify", "demo.recovery"],
            )
        )
        self.workspace_root = workspace_root
        self.scenario = scenario

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        if self.scenario == "no_code_changes":
            return SkillOutput(
                success=True,
                summary="Recovery demo intentionally produced no code changes",
                data={
                    "changed_files": [],
                    "patch_summary": "No-op coding step for failure demo",
                    "error": "no_code_changes",
                },
            )

        target = self.workspace_root / "calc.py"
        target.write_text(
            "def add(a: int, b: int) -> int:\n    return a + b\n",
            encoding="utf-8",
        )
        future_timestamp = time.time() + 2
        os.utime(target, (future_timestamp, future_timestamp))
        return SkillOutput(
            success=True,
            summary="calc.py fixed",
            data={
                "changed_files": ["calc.py"],
                "patch_summary": "Updated add() to use addition",
                "scenario": self.scenario,
            },
        )


def _build_demo_registry(*, workspace_root: Path, scenario: RecoveryDemoScenario) -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(
        PlanningSkill(
            SkillSpec(
                name="planning",
                description="Generate a minimal task graph for a user goal.",
                skill_type=SkillType.COMPOSITE,
                capabilities=["graph.plan"],
            ),
            default_planning_mode="rule_based",
        )
    )
    registry.register(
        RepoAnalysisSkill(
            SkillSpec(
                name="analyze_repo",
                description="Inspect the repository and expose a lightweight profile.",
                skill_type=SkillType.COMPOSITE,
                capabilities=["repo.inspect"],
            )
        )
    )
    registry.register(DemoRecoveryCodingSkill(workspace_root=workspace_root, scenario=scenario))
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
            ),
            skill_executor=skill_executor,
        )
    )
    return registry


async def run_v3_recovery_demo(*, scenario: RecoveryDemoScenario = "success") -> dict[str, object]:
    """Run a deterministic V3 recovery demo and return the full run result."""
    workspace_root = _build_recovery_demo_workspace()
    registry = _build_demo_registry(workspace_root=workspace_root, scenario=scenario)

    result = await run_v3(
        goal="run tests and recover",
        workdir=str(workspace_root),
        include_events=True,
        include_trace=True,
        registry=registry,
    )
    return {
        **result,
        "scenario": scenario,
        "workdir": str(workspace_root),
        "task": "run tests and recover",
    }
