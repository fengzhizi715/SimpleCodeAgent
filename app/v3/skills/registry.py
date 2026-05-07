"""Skill registry for V3."""

from __future__ import annotations

from app.v3.skills.base import Skill


class SkillRegistry:
    """In-memory skill registry."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """Register or replace a skill by name."""
        self._skills[skill.spec.name] = skill

    def get(self, name: str) -> Skill:
        """Get a skill by name."""
        skill = self._skills.get(name)
        if skill is None:
            raise ValueError(f"Skill not found: {name}")
        if not skill.spec.enabled:
            raise ValueError(f"Skill disabled: {name}")
        return skill

    def list(self) -> list[Skill]:
        """List registered skills."""
        return list(self._skills.values())
