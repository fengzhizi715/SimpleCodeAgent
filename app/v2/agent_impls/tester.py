"""Tester agent implementation."""

from __future__ import annotations

from app.contracts.agent import AgentArtifact, AgentResult, AgentSpec, AgentTask, SharedWorkspace, TestReport
from app.contracts.run import RunMetrics
from app.v2.agent_impls.llm_utils import parse_tool_content
from app.v2.base import AgentBase, AgentContext


class TesterAgent(AgentBase):
    """运行受控测试命令并输出结构化测试报告。

    输入契约：
    - task.goal 与 task.input_data.command（可选）决定测试命令。
    - prompt_context.coder_context 提供变更文件，用于优先窄范围测试。
    - context.tool_registry：必须可用 shell_run。

    输出契约：
    - AgentResult.status：completed；测试未通过时多为 retryable；若未收集到任何用例则为 failed（no_tests_collected）。
    - output_data.test_report：结构化 TestReport（status、failure_type、key_logs 等）。
    - artifacts：latest_test_result 工件。
    """

    DEFAULT_COMMAND = "pytest -q"

    def __init__(self) -> None:
        super().__init__(
            AgentSpec(
                agent_id="tester",
                role="tester",
                description="Run verification commands and summarize failures.",
                capabilities=["test", "build-check", "failure-analysis"],
            )
        )

    def run(
        self,
        *,
        task: AgentTask,
        workspace: SharedWorkspace,
        context: AgentContext,
        prompt_context: dict[str, object],
    ) -> AgentResult:
        command_candidates = self._select_command_candidates(task=task, prompt_context=prompt_context)
        command = command_candidates[0]
        shell_result = context.tool_registry.execute_tool(
            tool_name="shell_run",
            arguments={"command": command, "workdir": "."},
            tool_call_id=f"{task.task_id}-shell-run",
        )
        payload = parse_tool_content(shell_result.content)
        stdout = str(payload.get("stdout") or "")
        stderr = str(payload.get("stderr") or "")
        if shell_result.is_error:
            report = TestReport(
                status="blocked",
                executed_command=command,
                summary="测试命令未能执行，当前步骤被阻塞。",
                failure_type="command_blocked",
                key_logs=[str(payload.get("error") or shell_result.content)],
                suggested_next_action="调整测试命令或执行环境后重试。",
            )
            return AgentResult(
                task_id=task.task_id,
                agent_id=self.spec.agent_id,
                status="failed",
                summary=report.summary,
                metrics=RunMetrics(tool_call_count=1, tool_error_count=1),
                output_data={
                    "test_report": report.model_dump(),
                    "command_candidates": command_candidates,
                },
                artifacts=[
                    AgentArtifact(
                        key="latest_test_result",
                        type="test-report",
                        summary=report.summary,
                        producer_agent=self.spec.agent_id,
                        content=report.model_dump(),
                    )
                ],
                error_message=report.summary,
                next_action=report.suggested_next_action,
            )
        ok = bool(payload.get("ok"))
        key_logs = [line for line in (stdout + "\n" + stderr).splitlines() if line.strip()][:12]
        failure_type = None if ok else self._infer_failure_type(stdout=stdout, stderr=stderr)
        if not ok and failure_type == "no_tests_collected":
            summary = (
                "未在仓库中收集到可运行的测试用例（常见于根目录直接 pytest 但项目为 Gradle/Maven 等）。"
                " 请调整验证命令或先由分析步骤确认构建/测试入口。"
            )
            suggested = "不要按普通测试失败回流 Coder；应更新测试命令（如 ./gradlew test）或先分析项目结构。"
        else:
            summary = "测试通过。" if ok else "测试失败，需要根据日志继续修复。"
            suggested = None if ok else "将失败日志回流给 Coder 进行修复。"
        report = TestReport(
            status="passed" if ok else "failed",
            executed_command=command,
            summary=summary,
            failure_type=failure_type,
            key_logs=key_logs,
            suggested_next_action=suggested,
        )
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.spec.agent_id,
            status="completed" if ok else ("failed" if failure_type == "no_tests_collected" else "retryable"),
            summary=report.summary,
            metrics=RunMetrics(tool_call_count=1),
            output_data={
                "test_report": report.model_dump(),
                "command_candidates": command_candidates,
                "selected_command": command,
                "stdout": stdout,
                "stderr": stderr,
            },
            artifacts=[
                AgentArtifact(
                    key="latest_test_result",
                    type="test-report",
                    summary=report.summary,
                    producer_agent=self.spec.agent_id,
                    content=report.model_dump(),
                )
            ],
            next_action=report.suggested_next_action,
        )

    def _select_command_candidates(
        self,
        *,
        task: AgentTask,
        prompt_context: dict[str, object],
    ) -> list[str]:
        explicit = str(task.input_data.get("command") or "").strip()
        if explicit:
            return [explicit]
        candidates: list[str] = []
        coder_context = prompt_context.get("coder_context")
        changed_files: list[str] = []
        if isinstance(coder_context, dict):
            for key in ("modified_files", "created_files"):
                values = coder_context.get(key, [])
                if isinstance(values, list):
                    changed_files.extend(str(value) for value in values)
        if self._looks_like_gradle_kotlin_project(prompt_context):
            wrapper = self._gradle_command_prefix(prompt_context)
            goal = task.goal.lower()
            if "test" in goal or "测试" in task.goal:
                candidates.append(f"{wrapper} test")
            candidates.append(f"{wrapper} compileKotlin")
            candidates.append(f"{wrapper} compileKotlinJvm")
            candidates.append(f"{wrapper} test")
        test_files = [path for path in changed_files if path.startswith("tests/") and path.endswith(".py")]
        if test_files:
            candidates.append(f"pytest -q {' '.join(test_files[:5])}")
        if "pytest" in task.goal.lower() or "测试" in task.goal:
            candidates.append("pytest -q")
        if not candidates:
            candidates.append(self.DEFAULT_COMMAND)
        deduped: list[str] = []
        for candidate in candidates:
            if candidate not in deduped:
                deduped.append(candidate)
        return deduped

    def _looks_like_gradle_kotlin_project(self, prompt_context: dict[str, object]) -> bool:
        analysis_context = prompt_context.get("analysis_context")
        if not isinstance(analysis_context, dict):
            analysis_context = {}
        repo_profile = str(analysis_context.get("repo_profile") or "").lower()
        if repo_profile == "gradle_kotlin":
            return True
        project_summary = str(prompt_context.get("project_summary") or "").lower()
        build_system = str(analysis_context.get("build_system") or "").lower()
        if "gradle" in project_summary or "gradle" in build_system:
            return True
        key_files = analysis_context.get("key_files", [])
        if isinstance(key_files, list):
            for item in key_files:
                if isinstance(item, dict):
                    path = str(item.get("path") or "")
                else:
                    path = str(item)
                if path.endswith(("build.gradle.kts", "settings.gradle.kts")):
                    return True
        root_entries = analysis_context.get("root_entries", [])
        if isinstance(root_entries, list):
            names = {
                str(item.get("name"))
                for item in root_entries
                if isinstance(item, dict) and item.get("name")
            }
            if {"build.gradle.kts", "settings.gradle.kts", "gradlew"} & names:
                return True
        return False

    def _gradle_command_prefix(self, prompt_context: dict[str, object]) -> str:
        analysis_context = prompt_context.get("analysis_context")
        if not isinstance(analysis_context, dict):
            return "./gradlew"
        root_entries = analysis_context.get("root_entries", [])
        if isinstance(root_entries, list):
            names = {
                str(item.get("name"))
                for item in root_entries
                if isinstance(item, dict) and item.get("name")
            }
            if "gradlew" not in names:
                return "gradle"
        return "./gradlew"

    def _infer_failure_type(self, *, stdout: str, stderr: str) -> str:
        combined = f"{stdout}\n{stderr}".lower()
        if (
            "no tests ran" in combined
            or "collected 0 items" in combined
            or "0 tests collected" in combined
        ):
            return "no_tests_collected"
        if "timed out" in combined or "timeout" in combined:
            return "timeout"
        if "assert" in combined:
            return "assertion_error"
        if "importerror" in combined or "modulenotfounderror" in combined:
            return "import_error"
        if "syntaxerror" in combined:
            return "syntax_error"
        if "typeerror" in combined:
            return "type_error"
        if "attributeerror" in combined:
            return "attribute_error"
        if "failed" in combined:
            return "test_failure"
        return "unknown"
