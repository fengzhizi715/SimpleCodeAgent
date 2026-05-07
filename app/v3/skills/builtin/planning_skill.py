"""Built-in planning skill for V3."""

from __future__ import annotations

from app.v3.skills.base import Skill
from app.v3.contracts.skill_contracts import SkillInput, SkillOutput


class PlanningSkill(Skill):
    """Generate a small graph from a user goal."""

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        user_goal = str(skill_input.payload.get("goal", "")).strip()
        graph = {
            "graph_id": f"graph_for_{skill_input.run_id}",
            "run_id": skill_input.run_id,
            "nodes": [
                {
                    "node_id": "code",
                    "skill_name": "coding",
                    "input_payload": {"goal": user_goal},
                    "dependencies": [],
                }
            ],
        }
        return SkillOutput(
            success=True,
            summary=f"Generated graph for goal: {user_goal or 'unspecified goal'}",
            data={"graph": graph},
        )
