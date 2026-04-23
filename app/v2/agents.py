"""V2 核心 Agent 实现。"""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.message import ChatMessage
from app.contracts.agent import (
    AgentArtifact,
    AgentResult,
    ReviewIssue,
    AgentSpec,
    AgentTask,
    SharedWorkspace,
    TestReport,
)
from app.contracts.planner import Plan, PlanStep, PlanStepType
from app.contracts.run import RunRequest
from app.v1.planner.simple_planner import SimplePlanner
from app.v1.runtime.loop import AgentLoop
from app.v2.base import AgentBase, AgentContext

IGNORED_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    ".traces",
    ".chroma",
    "node_modules",
    "dist",
    "build",
}
TEXT_FILE_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".sh",
    ".sql",
}
PLANNER_TOOL_HINTS: dict[str, str] = {
    "analysis": "file_search",
    "coding": "write_file",
    "testing": "shell_run",
    "planning": None,  # type: ignore[assignment]
    "validation": "shell_run",
    "general": None,  # type: ignore[assignment]
}


class PlannerStepPayload(BaseModel):
    """LLM planner 输出的单步骤结构。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str
    goal: str
    type: PlanStepType = "general"
    description: str = ""
    suggested_agent: Literal["analyst", "coder", "tester"] = "coder"
    input_requirements: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    max_retries: int = 1


class PlannerOutputPayload(BaseModel):
    """LLM planner 输出结构。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    summary: str
    steps: list[PlannerStepPayload]


class AnalysisFilePayload(BaseModel):
    """项目分析中的关键文件条目。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    path: str
    reason: str


class AnalystOutputPayload(BaseModel):
    """Analyst Agent 结构化输出。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    project_summary: str
    module_responsibilities: dict[str, str] = Field(default_factory=dict)
    entry_files: list[str] = Field(default_factory=list)
    key_files: list[AnalysisFilePayload] = Field(default_factory=list)
    coding_hints: list[str] = Field(default_factory=list)


class ReviewIssuePayload(BaseModel):
    """LLM reviewer 输出的问题条目。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    severity: Literal["low", "medium", "high"]
    title: str
    detail: str
    file_path: str | None = None


class ReviewOutputPayload(BaseModel):
    """LLM reviewer 输出结构。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    review_summary: str
    issues: list[ReviewIssuePayload] = Field(default_factory=list)
    recommended_action: str = ""


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _parse_tool_content(content: str) -> dict[str, object]:
    parsed = _extract_json_object(content)
    if parsed is None:
        return {"raw": content}
    return parsed


def _chat_json(
    *,
    context: AgentContext,
    system_prompt: str,
    user_prompt: str,
) -> dict[str, Any] | None:
    """调用 LLM 并尝试解析 JSON 对象输出。"""
    try:
        result = context.provider.chat(
            RunRequest(
                messages=[
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(role="user", content=user_prompt),
                ],
                model=context.model,
                reasoning_mode=context.reasoning_mode,
                temperature=0.0,
            )
        )
    except Exception:
        return None
    if not result.choices:
        return None
    content = result.choices[0].message.content or ""
    return _extract_json_object(content)


def _relative_path(workspace_root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(workspace_root))
    except ValueError:
        return str(path)


def _is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in TEXT_FILE_SUFFIXES or path.name in {
        "README",
        "README.md",
        "Makefile",
        "Dockerfile",
    }


def _snapshot_workspace(workspace_root: Path) -> dict[str, str]:
    """为 coder 前后对比拍一个轻量文本快照。"""
    snapshot: dict[str, str] = {}
    if not workspace_root.exists():
        return snapshot
    for path in workspace_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIR_NAMES for part in path.parts):
            continue
        if not _is_text_candidate(path):
            continue
        try:
            snapshot[_relative_path(workspace_root, path)] = path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            continue
    return snapshot


def _build_workspace_diff(
    *,
    workspace_root: Path,
    before: dict[str, str],
    after: dict[str, str],
) -> tuple[list[str], list[str], list[str], dict[str, str]]:
    created_files = sorted(path for path in after if path not in before)
    deleted_files = sorted(path for path in before if path not in after)
    modified_files = sorted(
        path for path in before if path in after and before[path] != after[path]
    )
    diff_previews: dict[str, str] = {}
    for path in created_files + modified_files:
        before_content = before.get(path, "")
        after_content = after.get(path, "")
        diff_lines = list(
            difflib.unified_diff(
                before_content.splitlines(),
                after_content.splitlines(),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                lineterm="",
            )
        )
        diff_previews[path] = "\n".join(diff_lines[:120])
    for path in deleted_files:
        before_content = before.get(path, "")
        diff_lines = list(
            difflib.unified_diff(
                before_content.splitlines(),
                [],
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                lineterm="",
            )
        )
        diff_previews[path] = "\n".join(diff_lines[:120])
    return modified_files, created_files, deleted_files, diff_previews


class PlannerAgent(AgentBase):
    """将用户目标转成结构化计划。"""

    def __init__(self, planner: SimplePlanner | None = None) -> None:
        super().__init__(
            AgentSpec(
                agent_id="planner",
                role="planner",
                description="Generate and revise structured execution plans.",
                capabilities=["plan", "replan", "step-routing"],
            )
        )
        self.planner = planner or SimplePlanner()

    def run(
        self,
        *,
        task: AgentTask,
        workspace: SharedWorkspace,
        context: AgentContext,
        prompt_context: dict[str, object],
    ) -> AgentResult:
        raw_plan = self._generate_plan(task=task, workspace=workspace, context=context, prompt_context=prompt_context)
        plan = Plan(
            summary=f"Plan for: {task.goal}",
            steps=[self._enrich_step(step) for step in raw_plan],
            replan_count=(workspace.current_plan.replan_count if workspace.current_plan else 0),
        )
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.spec.agent_id,
            status="completed",
            summary=f"生成 {len(plan.steps)} 个步骤的执行计划。",
            output_data={"plan": plan.model_dump()},
            artifacts=[
                AgentArtifact(
                    key="plan",
                    type="plan",
                    summary=plan.summary,
                    content=plan.model_dump(),
                )
            ],
        )

    def _generate_plan(
        self,
        *,
        task: AgentTask,
        workspace: SharedWorkspace,
        context: AgentContext,
        prompt_context: dict[str, object],
    ) -> list[PlanStep]:
        llm_plan = self._generate_plan_with_llm(
            task=task,
            workspace=workspace,
            context=context,
            prompt_context=prompt_context,
        )
        if llm_plan:
            return llm_plan
        if self.planner.should_plan(task.goal):
            return self.planner.create_plan(task.goal)
        return [PlanStep(title="执行任务", goal=task.goal, description=task.goal)]

    def _generate_plan_with_llm(
        self,
        *,
        task: AgentTask,
        workspace: SharedWorkspace,
        context: AgentContext,
        prompt_context: dict[str, object],
    ) -> list[PlanStep] | None:
        system_prompt = (
            "You are the Planner Agent for SimpleCodeAgent V2. "
            "Return only valid JSON with keys summary and steps. "
            "Each step must contain title, goal, type, description, suggested_agent, "
            "input_requirements, success_criteria, and max_retries. "
            "type must be one of analysis, coding, testing, planning, validation, general. "
            "suggested_agent must be one of analyst, coder, tester. "
            "Do not include markdown or explanations outside JSON."
        )
        user_prompt = "\n".join(
            [
                f"用户目标：{task.goal}",
                f"当前计划：{json.dumps(prompt_context.get('current_plan'), ensure_ascii=False)}",
                f"项目摘要：{prompt_context.get('project_summary', '')}",
                f"最近测试结果：{json.dumps(prompt_context.get('latest_test_result'), ensure_ascii=False)}",
                "请输出 2-5 个可执行步骤，优先保持中心化调度、先分析再编码再验证。",
            ]
        )
        payload = _chat_json(context=context, system_prompt=system_prompt, user_prompt=user_prompt)
        if payload is None:
            return None
        try:
            parsed = PlannerOutputPayload.model_validate(payload)
        except Exception:
            return None
        if not parsed.steps:
            return None
        return [
            PlanStep(
                title=item.title,
                goal=item.goal,
                type=item.type,
                description=item.description,
                suggested_agent=item.suggested_agent,
                input_requirements=item.input_requirements,
                success_criteria=item.success_criteria,
                max_retries=item.max_retries,
            )
            for item in parsed.steps
        ]

    def _enrich_step(self, step: PlanStep) -> PlanStep:
        suggested_agent = step.suggested_agent or self._suggest_agent(step)
        step_type = step.type if step.type != "general" else self._infer_step_type(step)
        goal = step.goal or step.description or step.title
        input_requirements = list(step.input_requirements)
        success_criteria = list(step.success_criteria)
        if not input_requirements:
            input_requirements = ["用户目标", "当前上下文"]
        if not success_criteria:
            success_criteria = ["输出可供下一步继续执行的结构化结果"]
        return step.model_copy(
            update={
                "goal": goal,
                "type": step_type,
                "suggested_agent": suggested_agent,
                "input_requirements": input_requirements,
                "success_criteria": success_criteria,
                "tool_name": step.tool_name or PLANNER_TOOL_HINTS.get(step_type),
            }
        )

    def _infer_step_type(self, step: PlanStep) -> str:
        text = f"{step.title} {step.description} {step.tool_name or ''}".lower()
        if any(keyword in text for keyword in ("测试", "验证", "pytest", "test", "shell_run")):
            return "testing"
        if any(keyword in text for keyword in ("查看", "搜索", "分析", "read", "search", "list")):
            return "analysis"
        if any(keyword in text for keyword in ("实现", "修复", "生成", "写入", "modify", "fix", "write")):
            return "coding"
        return "general"

    def _suggest_agent(self, step: PlanStep) -> str:
        if step.type == "testing" or step.tool_name == "shell_run":
            return "tester"
        if step.type == "analysis" or step.tool_name in {"list_dir", "read_file", "file_search", "retrieve_docs"}:
            return "analyst"
        if step.type == "coding" or step.tool_name in {"write_file", "replace_in_file", "multi_file_patch"}:
            return "coder"
        title = f"{step.title} {step.description}".lower()
        if "测试" in title or "test" in title:
            return "tester"
        if "分析" in title or "查看" in title or "search" in title:
            return "analyst"
        return "coder"


class AnalystAgent(AgentBase):
    """进行项目结构分析并写入共享上下文。"""

    def __init__(self) -> None:
        super().__init__(
            AgentSpec(
                agent_id="analyst",
                role="analyst",
                description="Analyze repository structure and prepare context for coding.",
                capabilities=["project-analysis", "file-discovery", "workspace-summary"],
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
        list_result = context.tool_registry.execute_tool(
            tool_name="list_dir",
            arguments={"path": ".", "max_entries": 50},
            tool_call_id=f"{task.task_id}-list-dir",
        )
        search_result = context.tool_registry.execute_tool(
            tool_name="file_search",
            arguments={"query": "class ", "glob": "app/**/*.py", "max_results": 12},
            tool_call_id=f"{task.task_id}-file-search",
        )
        list_payload = _parse_tool_content(list_result.content)
        search_payload = _parse_tool_content(search_result.content)
        entries = list_payload.get("entries", [])
        matches = search_payload.get("matches", [])
        key_files = self._pick_key_files(entries=entries, matches=matches, workspace_root=context.workspace_root)
        file_snippets = self._read_key_files(key_files=key_files, context=context, task=task)
        analysis_payload = self._generate_analysis_with_llm(
            task=task,
            context=context,
            entries=entries,
            matches=matches,
            key_files=key_files,
            file_snippets=file_snippets,
        )
        if analysis_payload is None:
            analysis_payload = self._build_fallback_analysis(
                task=task,
                entries=entries,
                matches=matches,
                key_files=key_files,
            )
        summary = analysis_payload.project_summary
        key_file_dicts = [item.model_dump() for item in analysis_payload.key_files]
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.spec.agent_id,
            status="completed",
            summary=summary,
            output_data={
                "project_summary": summary,
                "module_responsibilities": analysis_payload.module_responsibilities,
                "entry_files": analysis_payload.entry_files,
                "key_files": key_file_dicts,
                "coding_hints": analysis_payload.coding_hints,
                "root_entries": entries,
                "highlighted_files": matches[:5],
            },
            artifacts=[
                AgentArtifact(
                    key="project_summary",
                    type="analysis",
                    summary="项目结构分析完成",
                    content={
                        "project_summary": summary,
                        "module_responsibilities": analysis_payload.module_responsibilities,
                        "entry_files": analysis_payload.entry_files,
                        "key_files": key_file_dicts,
                        "coding_hints": analysis_payload.coding_hints,
                    },
                )
            ],
        )

    def _pick_key_files(
        self,
        *,
        entries: list[object],
        matches: list[object],
        workspace_root: Path,
    ) -> list[str]:
        selected: list[str] = []
        preferred = [
            "README.md",
            "pyproject.toml",
            "app/main.py",
            "app/api/routes/agent.py",
            "app/v1/runtime/loop.py",
            "app/v2/runtime.py",
        ]
        for candidate in preferred:
            if (workspace_root / candidate).exists():
                selected.append(candidate)
        for match in matches:
            if not isinstance(match, dict):
                continue
            match_path = str(match.get("path") or "")
            if not match_path:
                continue
            relative = _relative_path(workspace_root, Path(match_path))
            if relative not in selected:
                selected.append(relative)
            if len(selected) >= 6:
                break
        return selected[:6]

    def _read_key_files(
        self,
        *,
        key_files: list[str],
        context: AgentContext,
        task: AgentTask,
    ) -> dict[str, str]:
        snippets: dict[str, str] = {}
        for index, path in enumerate(key_files, start=1):
            result = context.tool_registry.execute_tool(
                tool_name="read_file",
                arguments={"path": path, "max_chars": 1200},
                tool_call_id=f"{task.task_id}-read-file-{index}",
            )
            payload = _parse_tool_content(result.content)
            content = str(payload.get("content") or "").strip()
            if content:
                snippets[path] = content
        return snippets

    def _generate_analysis_with_llm(
        self,
        *,
        task: AgentTask,
        context: AgentContext,
        entries: list[object],
        matches: list[object],
        key_files: list[str],
        file_snippets: dict[str, str],
    ) -> AnalystOutputPayload | None:
        system_prompt = (
            "You are the Analyst Agent for SimpleCodeAgent V2. "
            "Return only valid JSON with keys: project_summary, module_responsibilities, "
            "entry_files, key_files, coding_hints. "
            "module_responsibilities must be an object. key_files must be a list of {path, reason}. "
            "Keep the output concise and grounded in the provided repository observations."
        )
        user_prompt = "\n".join(
            [
                f"任务目标：{task.goal}",
                f"根目录条目：{json.dumps(entries[:20], ensure_ascii=False)}",
                f"搜索命中：{json.dumps(matches[:8], ensure_ascii=False)}",
                f"关键文件：{json.dumps(key_files, ensure_ascii=False)}",
                f"文件片段：{json.dumps(file_snippets, ensure_ascii=False)}",
            ]
        )
        payload = _chat_json(context=context, system_prompt=system_prompt, user_prompt=user_prompt)
        if payload is None:
            return None
        try:
            return AnalystOutputPayload.model_validate(payload)
        except Exception:
            return None

    def _build_fallback_analysis(
        self,
        *,
        task: AgentTask,
        entries: list[object],
        matches: list[object],
        key_files: list[str],
    ) -> AnalystOutputPayload:
        top_level_items = ", ".join(
            entry["name"] for entry in entries if isinstance(entry, dict) and entry.get("name")
        ) or "无"
        highlighted_files = [
            _relative_path(Path("."), Path(str(match["path"])))
            for match in matches[:5]
            if isinstance(match, dict) and match.get("path")
        ]
        module_responsibilities: dict[str, str] = {}
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("is_dir"):
                continue
            name = str(entry.get("name"))
            if name == "app":
                module_responsibilities["app"] = "应用主体代码，包含共享层和版本实现。"
            elif name == "docs":
                module_responsibilities["docs"] = "项目说明、架构与教学文档。"
            elif name == "tests":
                module_responsibilities["tests"] = "回归测试与基础验证。"
        return AnalystOutputPayload(
            project_summary=(
                f"项目根目录包含：{top_level_items}。"
                f" 任务分析目标：{task.goal}。"
            ),
            module_responsibilities=module_responsibilities,
            entry_files=[path for path in key_files if path.endswith(("main.py", "agent.py", "runtime.py"))][:4],
            key_files=[
                AnalysisFilePayload(path=path, reason="与当前任务或系统主链路高度相关")
                for path in key_files[:5]
            ],
            coding_hints=[
                "优先复用现有 contract 与 runtime 基础设施。",
                "保持 v1/v2 边界清晰，避免把 v2 逻辑回灌到共享层或 v1。",
                *([f"优先关注：{', '.join(highlighted_files)}"] if highlighted_files else []),
            ],
        )


class CoderAgent(AgentBase):
    """复用 V1 AgentLoop 执行局部编码任务。

    这里复用的是 v1 的“单任务执行单元”，不是第二个 orchestrator。
    v2 的多 Agent 调度仍然只由外层 OrchestratorRuntime 负责。
    """

    def __init__(self, agent_loop: AgentLoop | None = None) -> None:
        super().__init__(
            AgentSpec(
                agent_id="coder",
                role="coder",
                description="Implement focused code changes with local validation.",
                capabilities=["code-edit", "tool-use", "patch-summary"],
            )
        )
        self.agent_loop = agent_loop or AgentLoop()

    def run(
        self,
        *,
        task: AgentTask,
        workspace: SharedWorkspace,
        context: AgentContext,
        prompt_context: dict[str, object],
    ) -> AgentResult:
        before_snapshot = _snapshot_workspace(context.workspace_root)
        coder_task = self._build_task_prompt(task=task, prompt_context=prompt_context, workspace=workspace)
        result = self.agent_loop.run(
            provider=context.provider,
            model=context.model,
            task=coder_task,
            system_prompt=(
                "You are the Coder Agent in SimpleCodeAgent V2. "
                "Make local, minimal changes, respect existing boundaries, and summarize what changed."
            ),
            session_id=f"{context.session_id}:v2:coder",
            reasoning_mode=context.reasoning_mode,
            temperature=0.0,
            max_steps=max(task.max_retries + 2, 3),
            run_timeout_seconds=120,
            tool_registry=context.tool_registry,
            persist_session_memory=False,
            root_run_id=context.run_id,
            parent_run_id=context.run_id,
        )
        after_snapshot = _snapshot_workspace(context.workspace_root)
        modified_files, created_files, deleted_files, diff_previews = _build_workspace_diff(
            workspace_root=context.workspace_root,
            before=before_snapshot,
            after=after_snapshot,
        )
        summary = result.final_output.strip() or "Coder 未返回可解析摘要。"
        risk_notes = self._build_risk_notes(
            result=result,
            modified_files=modified_files,
            created_files=created_files,
            deleted_files=deleted_files,
        )
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.spec.agent_id,
            status="completed" if result.status == "completed" else "failed",
            summary=summary,
            output_data={
                "run_id": result.run_id,
                "step_count": result.step_count,
                "status": result.status,
                "final_output": result.final_output,
                "modified_files": modified_files,
                "created_files": created_files,
                "deleted_files": deleted_files,
                "diff_previews": diff_previews,
                "risk_notes": risk_notes,
            },
            artifacts=[
                AgentArtifact(
                    key="patch_summary",
                    type="patch",
                    summary=summary[:200],
                    producer_agent=self.spec.agent_id,
                    content={
                        "final_output": result.final_output,
                        "modified_files": modified_files,
                        "created_files": created_files,
                        "deleted_files": deleted_files,
                    },
                )
            ],
            error_message=None if result.status == "completed" else result.final_output,
        )

    def _build_task_prompt(
        self,
        *,
        task: AgentTask,
        prompt_context: dict[str, object],
        workspace: SharedWorkspace,
    ) -> str:
        parts = [
            f"任务目标：{task.goal}",
            f"成功标准：{'; '.join(task.success_criteria) or '完成当前步骤'}",
        ]
        project_summary = str(prompt_context.get("project_summary") or workspace.project_summary).strip()
        if project_summary:
            parts.append(f"项目分析：{project_summary}")
        analysis_context = prompt_context.get("analysis_context")
        if analysis_context:
            parts.append(f"分析详情：{json.dumps(analysis_context, ensure_ascii=False)}")
        latest_test_result = prompt_context.get("latest_test_result")
        if latest_test_result:
            parts.append(f"最新测试反馈：{json.dumps(latest_test_result, ensure_ascii=False)}")
        if workspace.latest_patch_summary:
            parts.append(f"最近代码改动摘要：{workspace.latest_patch_summary}")
        if task.constraints:
            parts.append(f"约束：{'; '.join(task.constraints)}")
        parts.append("完成后请明确说明修改了哪些文件、做了什么改动、还有什么风险。")
        return "\n".join(parts)

    def _build_risk_notes(
        self,
        *,
        result,
        modified_files: list[str],
        created_files: list[str],
        deleted_files: list[str],
    ) -> list[str]:
        notes: list[str] = []
        if result.status != "completed":
            notes.append("Coder 运行未完成，当前改动可能不完整。")
        if not modified_files and not created_files and not deleted_files:
            notes.append("未检测到工作区文件变化，可能只产生了建议而未真正修改文件。")
        if deleted_files:
            notes.append("存在文件删除，请确认是否符合最小改动原则。")
        return notes


class TesterAgent(AgentBase):
    """运行受控测试命令并输出结构化测试报告。"""

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
        payload = _parse_tool_content(shell_result.content)
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


class ReviewerAgent(AgentBase):
    """Review patch summary using rules plus optional LLM review."""

    def __init__(self) -> None:
        super().__init__(
            AgentSpec(
                agent_id="reviewer",
                role="reviewer",
                description="Review patch summary and identify maintainability or correctness risks.",
                capabilities=["review", "risk-analysis", "maintainability-check"],
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
        coder_context = prompt_context.get("coder_context")
        analysis_context = prompt_context.get("analysis_context")
        review_materials = self._collect_review_materials(
            context=context,
            coder_context=coder_context if isinstance(coder_context, dict) else {},
            analysis_context=analysis_context if isinstance(analysis_context, dict) else {},
            task=task,
        )
        rule_issues = self._build_review_issues(
            summary=workspace.latest_patch_summary,
            coder_context=coder_context if isinstance(coder_context, dict) else {},
            review_materials=review_materials,
        )
        llm_review = self._build_llm_review(
            summary=workspace.latest_patch_summary,
            coder_context=coder_context if isinstance(coder_context, dict) else {},
            analysis_context=analysis_context,
            project_summary=str(prompt_context.get("project_summary") or workspace.project_summary),
            review_materials=review_materials,
            context=context,
        )
        review_issues = self._merge_review_issues(rule_issues=rule_issues, llm_review=llm_review)
        summary = self._build_review_summary(review_issues=review_issues, llm_review=llm_review)
        output_data = {
            "review_summary": summary,
            "issues": [issue.model_dump() for issue in review_issues],
            "diff_previews": review_materials["diff_previews"],
            "changed_file_snippets": review_materials["changed_file_snippets"],
            "key_file_snippets": review_materials["key_file_snippets"],
            "recommended_action": self._build_recommended_action(
                review_issues=review_issues,
                llm_review=llm_review,
            ),
            "rule_issue_count": len(rule_issues),
            "llm_review_used": llm_review is not None,
        }
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.spec.agent_id,
            status="completed",
            summary=summary,
            output_data=output_data,
            artifacts=[
                AgentArtifact(
                    key="review_report",
                    type="review",
                    summary=summary,
                    producer_agent=self.spec.agent_id,
                    content=output_data,
                )
            ],
        )

    def _build_review_issues(
        self,
        *,
        summary: str,
        coder_context: dict[str, object],
        review_materials: dict[str, dict[str, str]],
    ) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        modified_files = [str(item) for item in coder_context.get("modified_files", []) if str(item).strip()]
        created_files = [str(item) for item in coder_context.get("created_files", []) if str(item).strip()]
        deleted_files = [str(item) for item in coder_context.get("deleted_files", []) if str(item).strip()]
        risk_notes = [str(item) for item in coder_context.get("risk_notes", []) if str(item).strip()]
        diff_previews = review_materials.get("diff_previews", {})
        if not modified_files and not created_files and not deleted_files:
            issues.append(
                ReviewIssue(
                    severity="medium",
                    title="未检测到实际文件改动",
                    detail="Coder 输出了摘要，但没有检测到文件变化，建议确认是否真的完成修改。",
                )
            )
        if deleted_files:
            issues.append(
                ReviewIssue(
                    severity="high",
                    title="存在文件删除",
                    detail="本次修改包含文件删除，请确认不会破坏现有行为或教学路径。",
                    file_path=deleted_files[0],
                )
            )
        if len(modified_files) + len(created_files) > 6:
            issues.append(
                ReviewIssue(
                    severity="medium",
                    title="改动范围偏大",
                    detail="当前改动涉及文件较多，建议检查是否偏离了“局部修改”的目标。",
                )
            )
        if any("未检测到工作区文件变化" in note for note in risk_notes):
            issues.append(
                ReviewIssue(
                    severity="medium",
                    title="修改未落盘风险",
                    detail="存在仅生成建议未真正写入文件的风险，建议在测试前再次确认。",
                )
            )
        if summary and "风险" in summary and not issues:
            issues.append(
                ReviewIssue(
                    severity="low",
                    title="需人工复核",
                    detail="Coder 摘要中提到了风险，建议在继续前做人工确认。",
                )
            )
        if any(path.startswith("app/contracts/") for path in modified_files):
            issues.append(
                ReviewIssue(
                    severity="medium",
                    title="修改了共享协议层",
                    detail="本次改动涉及共享 contract，建议额外检查是否会影响 v1/v2 的边界稳定性。",
                    file_path=next(path for path in modified_files if path.startswith("app/contracts/")),
                )
            )
        if any(path.startswith("app/v1/") for path in modified_files + created_files + deleted_files):
            issues.append(
                ReviewIssue(
                    severity="high",
                    title="触及 v1 代码路径",
                    detail="当前任务处于 v2 演进阶段，但改动触及了 v1 目录，建议重点确认没有破坏 v1 稳定性。",
                    file_path=next(
                        path
                        for path in modified_files + created_files + deleted_files
                        if path.startswith("app/v1/")
                    ),
                )
            )
        if not any(path.startswith("tests/") for path in modified_files + created_files) and (
            modified_files or created_files or deleted_files
        ):
            issues.append(
                ReviewIssue(
                    severity="medium",
                    title="缺少测试改动",
                    detail="当前代码发生了实际修改，但未检测到测试文件变更，建议确认是否已有足够覆盖。",
                )
            )
        for path, preview in diff_previews.items():
            if not preview.strip():
                continue
            lowered = preview.lower()
            if "except Exception" in preview or "except:" in lowered:
                issues.append(
                    ReviewIssue(
                        severity="medium",
                        title="存在宽泛异常捕获",
                        detail="diff 中出现了宽泛异常捕获，建议确认是否会掩盖真实错误。",
                        file_path=path,
                    )
                )
            if "TODO" in preview or "FIXME" in preview:
                issues.append(
                    ReviewIssue(
                        severity="low",
                        title="遗留 TODO/FIXME",
                        detail="本次改动中包含 TODO/FIXME 标记，建议确认是否适合作为当前阶段提交内容。",
                        file_path=path,
                    )
                )
        return issues

    def _build_llm_review(
        self,
        *,
        summary: str,
        coder_context: dict[str, object],
        analysis_context: object,
        project_summary: str,
        review_materials: dict[str, dict[str, str]],
        context: AgentContext,
    ) -> ReviewOutputPayload | None:
        system_prompt = (
            "You are the Reviewer Agent for SimpleCodeAgent V2. "
            "Return only valid JSON with keys review_summary, issues, recommended_action. "
            "issues must be a list of objects with severity, title, detail, file_path. "
            "Focus on correctness risk, maintainability, boundary violations, and missing validation. "
            "Do not restate the input unless it is relevant to a review concern."
        )
        user_prompt = "\n".join(
            [
                f"项目摘要：{project_summary}",
                f"代码改动摘要：{summary}",
                f"Coder 上下文：{json.dumps(coder_context, ensure_ascii=False)}",
                f"Analyst 上下文：{json.dumps(analysis_context, ensure_ascii=False)}",
                f"Diff 预览：{json.dumps(review_materials.get('diff_previews', {}), ensure_ascii=False)}",
                f"改动文件片段：{json.dumps(review_materials.get('changed_file_snippets', {}), ensure_ascii=False)}",
                f"关键文件片段：{json.dumps(review_materials.get('key_file_snippets', {}), ensure_ascii=False)}",
                "请做一次简洁但严格的 code review，指出 0-5 个最重要的问题。",
            ]
        )
        payload = _chat_json(context=context, system_prompt=system_prompt, user_prompt=user_prompt)
        if payload is None:
            return None
        try:
            return ReviewOutputPayload.model_validate(payload)
        except Exception:
            return None

    def _merge_review_issues(
        self,
        *,
        rule_issues: list[ReviewIssue],
        llm_review: ReviewOutputPayload | None,
    ) -> list[ReviewIssue]:
        merged: dict[tuple[str, str | None], ReviewIssue] = {
            (issue.title, issue.file_path): issue for issue in rule_issues
        }
        if llm_review is None:
            return list(merged.values())
        severity_rank = {"low": 1, "medium": 2, "high": 3}
        for item in llm_review.issues:
            key = (item.title, item.file_path)
            candidate = ReviewIssue(
                severity=item.severity,
                title=item.title,
                detail=item.detail,
                file_path=item.file_path,
            )
            existing = merged.get(key)
            if existing is None:
                merged[key] = candidate
                continue
            if severity_rank[candidate.severity] > severity_rank[existing.severity]:
                merged[key] = candidate
            elif len(candidate.detail) > len(existing.detail):
                merged[key] = candidate
        return sorted(
            merged.values(),
            key=lambda issue: (
                {"high": 0, "medium": 1, "low": 2}[issue.severity],
                issue.title,
            ),
        )

    def _build_review_summary(
        self,
        *,
        review_issues: list[ReviewIssue],
        llm_review: ReviewOutputPayload | None,
    ) -> str:
        if llm_review is not None and llm_review.review_summary.strip():
            if review_issues:
                return llm_review.review_summary.strip()
            return llm_review.review_summary.strip() or "Review 未发现明显阻塞问题。"
        if not review_issues:
            return "Review 未发现明显阻塞问题。"
        high_count = sum(issue.severity == "high" for issue in review_issues)
        medium_count = sum(issue.severity == "medium" for issue in review_issues)
        return f"Review 发现 {len(review_issues)} 个需要关注的问题，其中高风险 {high_count} 个、中风险 {medium_count} 个。"

    def _build_recommended_action(
        self,
        *,
        review_issues: list[ReviewIssue],
        llm_review: ReviewOutputPayload | None,
    ) -> str:
        if llm_review is not None and llm_review.recommended_action.strip():
            return llm_review.recommended_action.strip()
        if any(issue.severity == "high" for issue in review_issues):
            return "建议先处理高风险 review 问题，再进入测试验证。"
        if any(issue.severity == "medium" for issue in review_issues):
            return "建议优先处理中风险 review 问题，再继续后续验证。"
        return "可以继续进入测试验证。"

    def _collect_review_materials(
        self,
        *,
        context: AgentContext,
        coder_context: dict[str, object],
        analysis_context: dict[str, object],
        task: AgentTask,
    ) -> dict[str, dict[str, str]]:
        diff_previews = {
            str(path): str(preview)
            for path, preview in (coder_context.get("diff_previews", {}) or {}).items()
            if str(path).strip() and str(preview).strip()
        }
        changed_files = []
        for key in ("modified_files", "created_files"):
            values = coder_context.get(key, [])
            if isinstance(values, list):
                changed_files.extend(str(value) for value in values if str(value).strip())
        changed_file_snippets = self._read_file_snippets(
            context=context,
            paths=changed_files[:4],
            task=task,
            prefix="review-changed",
        )
        key_files: list[str] = []
        raw_key_files = analysis_context.get("key_files", [])
        if isinstance(raw_key_files, list):
            for item in raw_key_files[:4]:
                if isinstance(item, dict) and item.get("path"):
                    key_files.append(str(item["path"]))
                elif isinstance(item, str):
                    key_files.append(item)
        key_file_snippets = self._read_file_snippets(
            context=context,
            paths=key_files,
            task=task,
            prefix="review-key",
        )
        return {
            "diff_previews": diff_previews,
            "changed_file_snippets": changed_file_snippets,
            "key_file_snippets": key_file_snippets,
        }

    def _read_file_snippets(
        self,
        *,
        context: AgentContext,
        paths: list[str],
        task: AgentTask,
        prefix: str,
    ) -> dict[str, str]:
        snippets: dict[str, str] = {}
        for index, path in enumerate(paths, start=1):
            result = context.tool_registry.execute_tool(
                tool_name="read_file",
                arguments={"path": path, "max_chars": 1200},
                tool_call_id=f"{task.task_id}-{prefix}-{index}",
            )
            payload = _parse_tool_content(result.content)
            content = str(payload.get("content") or "").strip()
            if content:
                snippets[path] = content
        return snippets
