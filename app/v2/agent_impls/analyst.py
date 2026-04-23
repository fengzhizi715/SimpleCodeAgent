"""Analyst agent implementation."""

from __future__ import annotations

import json
from pathlib import Path

from app.contracts.agent import AgentArtifact, AgentResult, AgentSpec, AgentTask, SharedWorkspace
from app.v2.agent_impls.llm_utils import chat_json, parse_tool_content
from app.v2.agent_impls.payloads import (
    AnalysisFilePayload,
    AnalystOutputPayload,
)
from app.v2.agent_impls.workspace_diff import relative_path
from app.v2.base import AgentBase, AgentContext


class AnalystAgent(AgentBase):
    """进行项目结构分析并写入共享上下文。

    输入契约：
    - task.goal：当前分析目标。
    - context.tool_registry：必须可用 list_dir / file_search / read_file。
    - prompt_context：可选的项目提示信息。

    输出契约：
    - AgentResult.status：completed。
    - output_data.project_summary / module_responsibilities / key_files。
    - artifacts：project_summary 分析工件。
    """

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
        list_payload = parse_tool_content(list_result.content)
        search_payload = parse_tool_content(search_result.content)
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
            relative = relative_path(workspace_root, Path(match_path))
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
            payload = parse_tool_content(result.content)
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
        payload = chat_json(context=context, system_prompt=system_prompt, user_prompt=user_prompt)
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
            relative_path(Path("."), Path(str(match["path"])))
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
