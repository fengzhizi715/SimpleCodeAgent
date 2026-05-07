"""Base skill abstraction for V3."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.v3.contracts.skill_contracts import SkillInput, SkillOutput, SkillSpec


class Skill(ABC):
    """Abstract V3 skill."""

    def __init__(self, spec: SkillSpec) -> None:
        self.spec = spec

    @abstractmethod
    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        """Execute the skill."""
