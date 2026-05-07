"""Built-in test runner skill for V3."""

from __future__ import annotations

from pathlib import Path

from app.v3.adapters.v1_tool_adapter import V1ToolAdapter
from app.v3.contracts.skill_contracts import SkillInput, SkillOutput
from app.v3.skills.base import Skill
from app.v3.skills.builtin.project_profile import inspect_workspace


class TestRunnerSkill(Skill):
    """Run a controlled verification command through the V1 shell adapter."""

    def __init__(self, spec, shell_adapter: V1ToolAdapter) -> None:
        super().__init__(spec)
        self.shell_adapter = shell_adapter

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        command = self._select_command(skill_input)
        workdir = str(skill_input.payload.get("workdir") or ".")
        result = await self.shell_adapter.run(
            {
                "command": command,
                "workdir": workdir,
                "timeout": int(skill_input.payload.get("timeout", 60)),
            }
        )

        ok = bool(result.get("ok"))
        stdout = str(result.get("stdout") or "")
        stderr = str(result.get("stderr") or "")
        failure_type = None if ok else self._infer_failure_type(stdout=stdout, stderr=stderr)

        if ok:
            return SkillOutput(
                success=True,
                summary=f"Tests passed: {command}",
                data={
                    "executed_command": command,
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": result.get("exit_code"),
                },
            )

        return SkillOutput(
            success=False,
            summary=f"Tests failed: {command}",
            error=failure_type or "test_failure",
            data={
                "executed_command": command,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": result.get("exit_code"),
                "failure_type": failure_type,
            },
        )

    def _select_command(self, skill_input: SkillInput) -> str:
        explicit = str(
            skill_input.payload.get("command")
            or skill_input.payload.get("test_command")
            or ""
        ).strip()
        if explicit:
            return explicit

        analyze_repo = skill_input.context.get("analyze_repo")
        if isinstance(analyze_repo, dict):
            commands = analyze_repo.get("candidate_test_commands", [])
            if isinstance(commands, list) and commands:
                return str(commands[0])

        workspace_root = (
            skill_input.payload.get("workspace_root")
            or skill_input.context.get("workspace_root")
            or "."
        )
        profile = inspect_workspace(str(workspace_root))
        commands = profile.get("candidate_test_commands", [])
        if isinstance(commands, list) and commands:
            return str(commands[0])

        changed_files = self._collect_changed_test_files(skill_input.context)
        if changed_files:
            limited = " ".join(changed_files[:5])
            return f"pytest -q {limited}"
        return "pytest -q"

    def _collect_changed_test_files(self, context: dict[str, object]) -> list[str]:
        changed_files: list[str] = []
        coding_result = context.get("coding")
        if isinstance(coding_result, dict):
            values = coding_result.get("changed_files", [])
            if isinstance(values, list):
                changed_files.extend(str(value) for value in values)

        normalized: list[str] = []
        for raw_path in changed_files:
            path = Path(raw_path)
            path_text = raw_path.replace("\\", "/")
            if path_text.startswith("tests/") and path.suffix == ".py":
                normalized.append(path_text)
        return normalized

    def _infer_failure_type(self, *, stdout: str, stderr: str) -> str:
        combined = f"{stdout}\n{stderr}".lower()
        if "collected 0 items" in combined or "no tests ran" in combined:
            return "no_tests_collected"
        if "timeout" in combined or "timed out" in combined:
            return "timeout"
        if "assert" in combined:
            return "assertion_error"
        if "syntaxerror" in combined:
            return "syntax_error"
        if "importerror" in combined or "modulenotfounderror" in combined:
            return "import_error"
        if "typeerror" in combined:
            return "type_error"
        return "test_failure"
