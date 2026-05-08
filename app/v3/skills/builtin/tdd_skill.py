"""Built-in TDD skill for V3."""

from __future__ import annotations

from pathlib import Path

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
        rounds: list[dict[str, object]] = []
        resume_from_failure = bool(skill_input.payload.get("resume_from_failure", False))
        source_event = skill_input.context.get("source_event")
        resumed_failure = self._build_resumed_failure_result(source_event) if resume_from_failure else None

        if resumed_failure is not None:
            fast_fail = self._should_fast_fail(resumed_failure)
            if fast_fail is not None:
                return SkillOutput(
                    success=False,
                    summary=fast_fail,
                    error=resumed_failure.get("error"),
                    data={"rounds": rounds, "last_test_result": resumed_failure},
                )
            coding_result = await self.skill_executor.execute(
                self.coding_skill_name,
                SkillInput(
                    run_id=skill_input.run_id,
                    payload=skill_input.payload,
                    context={
                        **skill_input.context,
                        "last_test_result": resumed_failure,
                        "round_index": 0,
                    },
                ),
            )
            if not coding_result.success:
                return SkillOutput(
                    success=False,
                    summary="TDD skill failed during recovery coding round",
                    error=coding_result.error or coding_result.summary,
                    data={"coding_result": coding_result.data, "rounds": rounds},
                )
            if not self._has_code_changes(coding_result.data):
                return SkillOutput(
                    success=False,
                    summary="TDD skill stopped because coding produced no file changes",
                    error="no_code_changes",
                    data={"coding_result": coding_result.data, "rounds": rounds},
                )

            verification_result = await self._run_verification_sequence(
                skill_input=skill_input,
                coding_result=coding_result.data,
                round_index=0,
            )
            rounds.append(
                {
                    "round_index": 0,
                    "phase": "trigger_recovery",
                    "coding_summary": coding_result.summary,
                    "verification_summary": verification_result.summary,
                    "verification_success": verification_result.success,
                    "verification_branch": verification_result.data.get("verification_branch_summary", {}),
                }
            )
            if verification_result.success:
                return SkillOutput(
                    success=True,
                    summary="TDD recovery finished after triggered fix and re-test",
                    data={
                        "coding_result": coding_result.data,
                        "test_result": verification_result.data,
                        "rounds": rounds,
                    },
                )
            branch_summary = verification_result.data.get("verification_branch_summary", {})
            if isinstance(branch_summary, dict) and branch_summary.get("failed_stage") == "full_suite":
                return SkillOutput(
                    success=False,
                    summary=verification_result.summary,
                    error=verification_result.error,
                    data={
                        "coding_result": coding_result.data,
                        "test_result": verification_result.data,
                        "verification_branch_summary": branch_summary,
                        "rounds": rounds,
                    },
                )

            last_error = verification_result.error or verification_result.summary

        start_round = 1 if resumed_failure is not None else 0
        for round_index in range(start_round, max_rounds):
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
                    data={"test_result": test_result.data, "rounds": rounds},
                )

            last_error = test_result.error or test_result.summary
            fast_fail = self._should_fast_fail(test_result.model_dump())
            if fast_fail is not None:
                return SkillOutput(
                    success=False,
                    summary=fast_fail,
                    error=test_result.error or test_result.summary,
                    data={"test_result": test_result.data, "rounds": rounds},
                )

            coding_result = await self.skill_executor.execute(
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
            rounds.append(
                {
                    "round_index": round_index,
                    "phase": "loop_recovery",
                    "test_summary": test_result.summary,
                    "coding_summary": coding_result.summary,
                    "coding_success": coding_result.success,
                }
            )
            if not coding_result.success:
                return SkillOutput(
                    success=False,
                    summary="TDD skill failed during coding round",
                    error=coding_result.error or coding_result.summary,
                    data={"test_result": test_result.data, "coding_result": coding_result.data, "rounds": rounds},
                )
            if not self._has_code_changes(coding_result.data):
                return SkillOutput(
                    success=False,
                    summary="TDD skill stopped because coding produced no file changes",
                    error="no_code_changes",
                    data={"test_result": test_result.data, "coding_result": coding_result.data, "rounds": rounds},
                )

        return SkillOutput(
            success=False,
            summary="TDD skill reached max rounds",
            error=last_error,
            data={"rounds": rounds},
        )

    def _build_resumed_failure_result(self, source_event: object) -> dict[str, object] | None:
        if not isinstance(source_event, dict):
            return None
        if source_event.get("event_type") != "test_failed":
            return None
        payload = source_event.get("payload")
        if not isinstance(payload, dict):
            return None
        return {
            "success": False,
            "summary": f"Tests failed: {payload.get('executed_command', 'pytest -q')}",
            "error": payload.get("failure_type") or "test_failure",
            "data": dict(payload),
        }

    async def _run_verification_sequence(
        self,
        *,
        skill_input: SkillInput,
        coding_result: dict[str, object],
        round_index: int,
    ) -> SkillOutput:
        commands = self._build_verification_commands(skill_input=skill_input, coding_result=coding_result)
        last_result: SkillOutput | None = None
        executed_count = 0
        for command in commands:
            last_result = await self.skill_executor.execute(
                self.test_skill_name,
                SkillInput(
                    run_id=skill_input.run_id,
                    payload={
                        **skill_input.payload,
                        "command": command,
                    },
                    context={
                        **skill_input.context,
                        "round_index": round_index,
                        "coding": coding_result,
                    },
                ),
            )
            if not last_result.success:
                branch_summary = {
                    "focused_commands_passed": commands[:executed_count],
                    "failed_command": command,
                    "failed_stage": "full_suite" if executed_count > 0 else "focused_scope",
                    "remaining_commands": commands[executed_count + 1 :],
                }
                data = dict(last_result.data)
                data["verification_branch_summary"] = branch_summary
                summary = (
                    "Focused verification passed, but full-suite verification still failed"
                    if executed_count > 0
                    else last_result.summary
                )
                return SkillOutput(
                    success=False,
                    summary=summary,
                    error=last_result.error,
                    data=data,
                )
            executed_count += 1
        if last_result is not None:
            data = dict(last_result.data)
            data["verification_branch_summary"] = {
                "focused_commands_passed": commands[:-1] if len(commands) > 1 else [],
                "failed_command": None,
                "failed_stage": None,
                "remaining_commands": [],
            }
            return SkillOutput(
                success=last_result.success,
                summary=last_result.summary,
                error=last_result.error,
                data=data,
            )
        return SkillOutput(success=False, summary="No verification command was generated", error="no_verification_command")

    def _build_verification_commands(
        self,
        *,
        skill_input: SkillInput,
        coding_result: dict[str, object],
    ) -> list[str]:
        commands: list[str] = []
        changed_test_files = self._collect_changed_test_files(coding_result)
        preferred_targets = [
            str(item)
            for item in skill_input.payload.get("preferred_test_targets", [])
            if str(item).strip()
        ]
        seen: set[str] = set()

        for target in changed_test_files + preferred_targets:
            command = self._target_to_command(target)
            if command not in seen:
                commands.append(command)
                seen.add(command)

        base_command = str(skill_input.payload.get("command") or "pytest -q").strip() or "pytest -q"
        if base_command not in seen:
            commands.append(base_command)
            seen.add(base_command)

        if not bool(skill_input.payload.get("verify_full_suite", False)):
            return commands[:1]

        full_suite_command = self._select_full_suite_command(skill_input)
        if full_suite_command and full_suite_command not in seen:
            commands.append(full_suite_command)
        return commands

    def _collect_changed_test_files(self, coding_result: dict[str, object]) -> list[str]:
        raw_files = coding_result.get("changed_files", [])
        if not isinstance(raw_files, list):
            return []
        normalized: list[str] = []
        for raw_path in raw_files:
            path_text = str(raw_path).replace("\\", "/")
            if path_text.startswith("tests/") and path_text.endswith(".py"):
                normalized.append(path_text)
        return normalized

    def _target_to_command(self, target: str) -> str:
        normalized = target.replace("\\", "/")
        if normalized.endswith(".py"):
            return f"pytest -q {normalized}"
        return normalized

    def _select_full_suite_command(self, skill_input: SkillInput) -> str:
        analyze_repo = skill_input.context.get("analyze_repo")
        if isinstance(analyze_repo, dict):
            commands = analyze_repo.get("candidate_test_commands", [])
            if isinstance(commands, list):
                for command in reversed(commands):
                    text = str(command).strip()
                    if text == "pytest -q" or text.endswith(" test"):
                        return text
        command = str(skill_input.payload.get("command") or "").strip()
        return command

    def _has_code_changes(self, coding_result: dict[str, object]) -> bool:
        for field in ("changed_files", "modified_files", "created_files", "deleted_files"):
            value = coding_result.get(field, [])
            if isinstance(value, list) and value:
                return True
        return False

    def _should_fast_fail(self, test_result: dict[str, object]) -> str | None:
        failure_type = str(test_result.get("error") or "").strip()
        if failure_type == "no_tests_collected":
            return "TDD skill stopped because no tests were collected"
        return None
