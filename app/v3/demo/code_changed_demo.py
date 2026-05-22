"""Stable demo: code_updated -> follow-up test / governance intercept."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any, Literal

from app.v3.adapters.v1_tool_adapter import V1ToolAdapter
from app.v3.contracts.graph_contracts import TaskGraph, TaskNode
from app.v3.contracts.skill_contracts import SkillInput, SkillOutput, SkillSpec, SkillType
from app.v3.contracts.trigger_contracts import TriggerRule
from app.v3.runner import run_v3
from app.v3.skills.base import Skill
from app.v3.skills.builtin.test_runner_skill import TestRunnerSkill
from app.v3.skills.registry import SkillRegistry


CodeChangedDemoScenario = Literal["follow_up_test", "governance_intercept"]


def _build_code_changed_demo_workspace() -> Path:
    root = Path(tempfile.mkdtemp(prefix="v3-code-changed-demo-"))
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


class DemoCodeChangedCodingSkill(Skill):
    """Deterministic coding skill for code_updated follow-up demos."""

    def __init__(self, *, workspace_root: Path) -> None:
        super().__init__(
            SkillSpec(
                name="coding",
                description="deterministic code_changed demo coder",
                skill_type=SkillType.COMPOSITE,
                capabilities=["code.modify", "demo.code_changed"],
                emits_events=["code_updated"],
            )
        )
        self.workspace_root = workspace_root

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        target = self.workspace_root / "calc.py"
        target.write_text(
            "def add(a: int, b: int) -> int:\n    return a + b\n",
            encoding="utf-8",
        )
        future_timestamp = time.time() + 2
        os.utime(target, (future_timestamp, future_timestamp))
        return SkillOutput(
            success=True,
            summary="calc.py updated for follow-up verification",
            data={
                "changed_files": ["calc.py"],
                "patch_summary": "Updated add() to use addition before follow-up test",
            },
        )


def _build_demo_registry(*, workspace_root: Path) -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(DemoCodeChangedCodingSkill(workspace_root=workspace_root))
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
    return registry


def _build_demo_graph(*, workspace_root: Path) -> TaskGraph:
    return TaskGraph(
        graph_id="graph-code-changed-demo",
        run_id="run-code-changed-demo",
        nodes=[
            TaskNode(
                node_id="coding",
                skill_name="coding",
                input_payload={
                    "goal": "Update calc.py and let the runtime verify it with a follow-up test.",
                    "workspace_root": str(workspace_root),
                },
            )
        ],
    )


def _build_trigger_rules(*, workspace_root: Path) -> list[TriggerRule]:
    return [
        TriggerRule(
            rule_id="code_updated_follow_up_test",
            event_type="code_updated",
            target_skill_name="test_runner",
            input_mapping={
                "command": "pytest -q",
                "workspace_root": str(workspace_root),
            },
            max_trigger_count_per_run=1,
        )
    ]


async def run_v3_code_changed_demo(
    *,
    scenario: CodeChangedDemoScenario = "follow_up_test",
) -> dict[str, Any]:
    """Run a stable code_updated follow-up demo with or without governance intercept."""
    workspace_root = _build_code_changed_demo_workspace()
    registry = _build_demo_registry(workspace_root=workspace_root)
    graph = _build_demo_graph(workspace_root=workspace_root)
    trigger_rules = _build_trigger_rules(workspace_root=workspace_root)
    max_triggers_per_run = 20 if scenario == "follow_up_test" else 0

    result = await run_v3(
        graph=graph,
        workdir=str(workspace_root),
        include_events=True,
        include_trace=True,
        registry=registry,
        trigger_rules=trigger_rules,
        max_triggers_per_run=max_triggers_per_run,
    )

    return {
        **result,
        "scenario": scenario,
        "workdir": str(workspace_root),
        "task": "code change -> follow-up test",
    }
