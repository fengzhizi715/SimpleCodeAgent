"""Built-in planning skill for V3."""

from __future__ import annotations

from app.v3.contracts.event_contracts import EventType
from app.v3.contracts.planning_contracts import PlanningResult, RecoveryStrategy
from app.v3.skills.base import Skill
from app.v3.contracts.skill_contracts import SkillInput, SkillOutput
from app.v3.skills.builtin.project_profile import infer_goal_kind, inspect_workspace


class PlanningSkill(Skill):
    """Generate a repo-aware graph from a user goal."""

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        user_goal = str(skill_input.payload.get("goal", "")).strip()
        workspace_root = (
            skill_input.payload.get("workspace_root")
            or skill_input.context.get("workspace_root")
            or "."
        )
        profile = inspect_workspace(str(workspace_root))
        goal_kind = infer_goal_kind(user_goal)
        commands = profile.get("candidate_test_commands", [])
        candidate_test_commands = [str(command) for command in commands] if isinstance(commands, list) else []
        candidate_test_targets = [
            str(target)
            for target in profile.get("candidate_test_targets", [])
            if isinstance(target, str)
        ]
        template_name, template_reason, planner_notes, nodes = self._build_graph_template(
            user_goal=user_goal,
            goal_kind=goal_kind,
            workspace_root=str(profile["workspace_root"]),
            candidate_test_commands=candidate_test_commands,
            candidate_test_targets=candidate_test_targets,
        )

        trigger_rules = self._build_trigger_templates(
            user_goal=user_goal,
            goal_kind=goal_kind,
            workspace_root=str(profile["workspace_root"]),
            test_command=self._select_full_suite_command(candidate_test_commands),
            candidate_test_targets=candidate_test_targets,
        )
        recovery_strategy = self._select_recovery_strategy(
            user_goal=user_goal,
            goal_kind=goal_kind,
        ) if trigger_rules else RecoveryStrategy.NONE
        planning_result = PlanningResult.model_validate(
            {
                "graph": {
                    "graph_id": f"graph_for_{skill_input.run_id}",
                    "run_id": skill_input.run_id,
                    "nodes": nodes,
                },
                "repo_profile": profile["repo_profile"],
                "goal_kind": goal_kind,
                "recovery_strategy": recovery_strategy.value,
                "template_name": template_name,
                "template_reason": template_reason,
                "planner_notes": planner_notes,
                "candidate_test_commands": candidate_test_commands,
                "candidate_test_targets": candidate_test_targets,
                "trigger_rules": trigger_rules,
            }
        )
        return SkillOutput(
            success=True,
            summary=(
                f"Generated {len(nodes)}-node graph for goal: "
                f"{user_goal or 'unspecified goal'}"
            ),
            data=planning_result.model_dump(mode="json"),
        )

    def _build_trigger_templates(
        self,
        *,
        user_goal: str,
        goal_kind: str,
        workspace_root: str,
        test_command: str,
        candidate_test_targets: list[str],
    ) -> list[dict[str, object]]:
        if goal_kind not in {"coding", "testing", "general"} or not test_command:
            return []

        recovery_strategy = self._select_recovery_strategy(user_goal=user_goal, goal_kind=goal_kind)
        fix_goal = (
            "A test step failed in this repository. "
            f"Fix the failing implementation with the smallest possible code change so `{test_command}` passes. "
            f"Original user goal: {user_goal or 'unspecified goal'}. "
            "Edit repository files directly and summarize the patch."
        )
        if recovery_strategy == RecoveryStrategy.FIX_AND_RETEST:
            return [
                {
                    "rule_id": "template_fix_and_retest_after_test_failed",
                    "event_type": EventType.TEST_FAILED.value,
                    "target_skill_name": "tdd",
                    "enabled": True,
                    "input_mapping": {
                        "goal": fix_goal,
                        "workspace_root": workspace_root,
                        "command": test_command,
                        "allow_mock_fallback": False,
                        "resume_from_failure": True,
                        "max_rounds": 2,
                        "success_criteria": [f"{test_command} passes"],
                        "preferred_test_targets": candidate_test_targets[:2],
                        "verify_full_suite": True,
                    },
                }
            ]
        return [
            {
                "rule_id": "template_fix_after_test_failed",
                "event_type": EventType.TEST_FAILED.value,
                "target_skill_name": "coding",
                "enabled": True,
                "input_mapping": {
                    "goal": fix_goal,
                    "workspace_root": workspace_root,
                    "allow_mock_fallback": False,
                    "success_criteria": [f"{test_command} passes"],
                },
            }
        ]

    def _select_recovery_strategy(self, *, user_goal: str, goal_kind: str) -> RecoveryStrategy:
        text = user_goal.lower()
        fix_only_markers = (
            "fix only",
            "only fix",
            "just fix",
            "只修复",
            "不要重跑",
            "不重跑",
        )
        if any(marker in text for marker in fix_only_markers):
            return RecoveryStrategy.FIX_ONLY

        fix_and_retest_markers = (
            "re-test",
            "retest",
            "run tests",
            "run the tests",
            "verify",
            "until pass",
            "执行测试",
            "运行测试",
            "重跑测试",
            "重新测试",
            "测试通过",
            "修到测试通过",
            "recover",
        )
        if goal_kind == "testing" or any(marker in text for marker in fix_and_retest_markers):
            return RecoveryStrategy.FIX_AND_RETEST
        return RecoveryStrategy.FIX_ONLY

    def _build_graph_template(
        self,
        *,
        user_goal: str,
        goal_kind: str,
        workspace_root: str,
        candidate_test_commands: list[str],
        candidate_test_targets: list[str],
    ) -> tuple[str, str, list[str], list[dict[str, object]]]:
        analyze_node = {
            "node_id": "analyze_repo",
            "skill_name": "analyze_repo",
            "input_payload": {
                "goal": user_goal,
                "workspace_root": workspace_root,
            },
            "dependencies": [],
        }
        if goal_kind == "analysis":
            return (
                "analysis_only",
                "Goal is analysis-oriented, so planning stops after repository inspection.",
                ["Selected analysis-only template because the goal does not require coding or test execution."],
                [analyze_node],
            )

        full_suite_command = self._select_full_suite_command(candidate_test_commands)
        focused_commands = [
            command
            for command in candidate_test_commands
            if command != full_suite_command
        ]

        if goal_kind == "testing" and focused_commands and self._should_use_branch_testing_template(user_goal):
            nodes = [analyze_node]
            for index, command in enumerate(focused_commands[:2], start=1):
                nodes.append(
                    {
                        "node_id": f"test_scope_{index}",
                        "skill_name": "test_runner",
                        "input_payload": {
                            "goal": user_goal,
                            "workspace_root": workspace_root,
                            "command": command,
                        },
                        "dependencies": ["analyze_repo"],
                    }
                )
            if full_suite_command:
                nodes.append(
                    {
                        "node_id": "test_full_suite",
                        "skill_name": "test_runner",
                        "input_payload": {
                            "goal": user_goal,
                            "workspace_root": workspace_root,
                            "command": full_suite_command,
                        },
                        "dependencies": [node["node_id"] for node in nodes[1:]],
                    }
                )
            return (
                "testing_branch_verify",
                "Goal asks for broader test verification, so the planner fans out focused test nodes before the full suite.",
                [
                    f"Detected focused test targets: {', '.join(candidate_test_targets[:2]) or 'none'}.",
                    "Selected branch verification template to expose intermediate failures before the full suite.",
                ],
                nodes,
            )

        nodes = [analyze_node]
        if goal_kind in {"coding", "general"}:
            nodes.append(
                {
                    "node_id": "coding",
                    "skill_name": "coding",
                    "input_payload": {
                        "goal": user_goal,
                        "workspace_root": workspace_root,
                    },
                    "dependencies": ["analyze_repo"],
                }
            )

        dependency = "coding" if goal_kind in {"coding", "general"} else "analyze_repo"
        if (
            goal_kind in {"coding", "general"}
            and focused_commands
            and self._should_use_scoped_verification_template(user_goal)
        ):
            focused_command = focused_commands[0]
            nodes.append(
                {
                    "node_id": "test_changed_scope",
                    "skill_name": "test_runner",
                    "input_payload": {
                        "goal": user_goal,
                        "workspace_root": workspace_root,
                        "command": focused_command,
                    },
                    "dependencies": [dependency],
                }
            )
            if full_suite_command:
                nodes.append(
                    {
                        "node_id": "test_full_suite",
                        "skill_name": "test_runner",
                        "input_payload": {
                            "goal": user_goal,
                            "workspace_root": workspace_root,
                            "command": full_suite_command,
                        },
                        "dependencies": ["test_changed_scope"],
                    }
                )
                return (
                    "coding_focus_then_full_suite",
                    "Goal asks for scoped verification, so the planner runs a focused test before the full suite.",
                    [
                        f"Focused verification command: {focused_command}.",
                        f"Full-suite verification command: {full_suite_command}.",
                    ],
                    nodes,
                )

        if goal_kind in {"coding", "testing", "general"} and full_suite_command:
            nodes.append(
                {
                    "node_id": "test_runner",
                    "skill_name": "test_runner",
                    "input_payload": {
                        "goal": user_goal,
                        "workspace_root": workspace_root,
                        "command": full_suite_command,
                    },
                    "dependencies": [dependency],
                }
            )
        return (
            "default",
            "Planner selected the default linear graph because no richer template was strongly indicated by the goal.",
            [
                f"Goal kind inferred as {goal_kind}.",
                f"Primary verification command: {full_suite_command or 'none'}.",
            ],
            nodes,
        )

    def _select_full_suite_command(self, candidate_test_commands: list[str]) -> str:
        if not candidate_test_commands:
            return ""
        for command in reversed(candidate_test_commands):
            if command.strip() == "pytest -q" or command.endswith(" test"):
                return command
        return candidate_test_commands[-1]

    def _should_use_branch_testing_template(self, user_goal: str) -> bool:
        text = user_goal.lower()
        return any(
            marker in text
            for marker in (
                "full sweep",
                "all tests",
                "分支",
                "分层测试",
                "多测试节点",
                "branch",
            )
        )

    def _should_use_scoped_verification_template(self, user_goal: str) -> bool:
        text = user_goal.lower()
        return any(
            marker in text
            for marker in (
                "scoped",
                "limited scope",
                "focus test",
                "限定范围",
                "小范围验证",
                "先跑相关测试",
            )
        )
