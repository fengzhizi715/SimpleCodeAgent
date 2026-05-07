"""Built-in planning skill for V3."""

from __future__ import annotations

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
        test_command = ""
        commands = profile.get("candidate_test_commands", [])
        if isinstance(commands, list) and commands:
            test_command = str(commands[0])

        nodes: list[dict[str, object]] = [
            {
                "node_id": "analyze_repo",
                "skill_name": "analyze_repo",
                "input_payload": {
                    "goal": user_goal,
                    "workspace_root": profile["workspace_root"],
                },
                "dependencies": [],
            }
        ]
        if goal_kind in {"coding", "general"}:
            nodes.append(
                {
                    "node_id": "coding",
                    "skill_name": "coding",
                    "input_payload": {
                        "goal": user_goal,
                        "workspace_root": profile["workspace_root"],
                    },
                    "dependencies": ["analyze_repo"],
                }
            )
        if goal_kind in {"coding", "testing", "general"} and test_command:
            nodes.append(
                {
                    "node_id": "test_runner",
                    "skill_name": "test_runner",
                    "input_payload": {
                        "goal": user_goal,
                        "workspace_root": profile["workspace_root"],
                        "command": test_command,
                    },
                    "dependencies": ["coding" if goal_kind in {"coding", "general"} else "analyze_repo"],
                }
            )

        graph = {
            "graph_id": f"graph_for_{skill_input.run_id}",
            "run_id": skill_input.run_id,
            "nodes": nodes,
        }
        return SkillOutput(
            success=True,
            summary=(
                f"Generated {len(nodes)}-node graph for goal: "
                f"{user_goal or 'unspecified goal'}"
            ),
            data={
                "graph": graph,
                "repo_profile": profile["repo_profile"],
                "goal_kind": goal_kind,
                "candidate_test_commands": commands,
            },
        )
