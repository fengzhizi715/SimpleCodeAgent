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
    - AgentResult.status：completed / retryable / failed。
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
        report = TestReport(
            status="passed" if ok else "failed",
            executed_command=command,
            summary="测试通过。" if ok else "测试失败，需要根据日志继续修复。",
            failure_type=None if ok else self._infer_failure_type(stdout=stdout, stderr=stderr),
            key_logs=key_logs,
            suggested_next_action=None if ok else "将失败日志回流给 Coder 进行修复。",
        )
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.spec.agent_id,
            status="completed" if ok else "retryable",
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

    def _infer_failure_type(self, *, stdout: str, stderr: str) -> str:
        combined = f"{stdout}\n{stderr}".lower()
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
