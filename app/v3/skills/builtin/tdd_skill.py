"""Built-in TDD skill for V3."""

from __future__ import annotations

from app.v3.skills.base import Skill
from app.v3.contracts.skill_contracts import SkillInput, SkillOutput
from app.v3.runtime.skill_executor import SkillExecutor


class TDDSkill(Skill):
    """A tiny composite TDD loop."""

    def __init__(
        self,
        spec,
        skill_executor: SkillExecutor,
        *,
        test_skill_name: str = "test_runner",
        coding_skill_name: str = "coding",
    ) -> None:
        super().__init__(spec)
        self.skill_executor = skill_executor
        self.test_skill_name = test_skill_name
        self.coding_skill_name = coding_skill_name

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        max_rounds = int(skill_input.payload.get("max_rounds", 2))
        last_error = "Tests still failing after max rounds"

        for round_index in range(max_rounds):
            test_result = await self.skill_executor.execute(
                self.test_skill_name,
                SkillInput(
                    run_id=skill_input.run_id,
                    payload=skill_input.payload,
                    context={
                        **skill_input.context,
                        "round_index": round_index,
                    },
                ),
            )
            if test_result.success:
                return SkillOutput(
                    success=True,
                    summary=f"TDD loop finished in round {round_index + 1}",
                    data={"test_result": test_result.data},
                )

            last_error = test_result.error or test_result.summary
            await self.skill_executor.execute(
                self.coding_skill_name,
                SkillInput(
                    run_id=skill_input.run_id,
                    payload=skill_input.payload,
                    context={
                        **skill_input.context,
                        "last_test_result": test_result.model_dump(),
                        "round_index": round_index,
                    },
                ),
            )

        return SkillOutput(
            success=False,
            summary="TDD skill reached max rounds",
            error=last_error,
        )
