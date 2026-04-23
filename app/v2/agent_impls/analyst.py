"""Analyst agent implementation."""

from __future__ import annotations

import json
from pathlib import Path

from app.contracts.agent import AgentArtifact, AgentResult, AgentSpec, AgentTask, SharedWorkspace
from app.contracts.run import RunMetrics, RunUsage
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
        tool_call_count = 0
        list_result = context.tool_registry.execute_tool(
            tool_name="list_dir",
            arguments={"path": ".", "max_entries": 50},
            tool_call_id=f"{task.task_id}-list-dir",
        )
        tool_call_count += 1
        search_result = context.tool_registry.execute_tool(
            tool_name="file_search",
            arguments={"query": "class ", "glob": "app/**/*.py", "max_results": 12},
            tool_call_id=f"{task.task_id}-file-search",
        )
        tool_call_count += 1
        list_payload = parse_tool_content(list_result.content)
        search_payload = parse_tool_content(search_result.content)
        entries = list_payload.get("entries", [])
        matches = search_payload.get("matches", [])
        key_files = self._pick_key_files(entries=entries, matches=matches, workspace_root=context.workspace_root)
        file_snippets, read_call_count = self._read_key_files(key_files=key_files, context=context, task=task)
        tool_call_count += read_call_count
        analysis_payload, usage = self._generate_analysis_with_llm(
            task=task,
            context=context,
            entries=entries,
            matches=matches,
            key_files=key_files,
            file_snippets=file_snippets,
        )
        metrics = RunMetrics(
            llm_call_count=1 if usage is not None else 0,
            tool_call_count=tool_call_count,
        )
        if analysis_payload is None:
            analysis_payload = self._build_fallback_analysis(
                task=task,
                entries=entries,
                matches=matches,
                key_files=key_files,
                workspace_root=context.workspace_root,
            )
            metrics.fallback_count += 1
        summary = analysis_payload.project_summary
        key_file_dicts = [item.model_dump() for item in analysis_payload.key_files]
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.spec.agent_id,
            status="completed",
            summary=summary,
            usage=usage,
            metrics=metrics,
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
    ) -> tuple[dict[str, str], int]:
        snippets: dict[str, str] = {}
        read_call_count = 0
        for index, path in enumerate(key_files, start=1):
            result = context.tool_registry.execute_tool(
                tool_name="read_file",
                arguments={"path": path, "max_chars": 1200},
                tool_call_id=f"{task.task_id}-read-file-{index}",
            )
            read_call_count += 1
            payload = parse_tool_content(result.content)
            content = str(payload.get("content") or "").strip()
            if content:
                snippets[path] = content
        return snippets, read_call_count

    def _generate_analysis_with_llm(
        self,
        *,
        task: AgentTask,
        context: AgentContext,
        entries: list[object],
        matches: list[object],
        key_files: list[str],
        file_snippets: dict[str, str],
    ) -> tuple[AnalystOutputPayload | None, RunUsage | None]:
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
        payload, llm_result = chat_json(context=context, system_prompt=system_prompt, user_prompt=user_prompt)
        if payload is None:
            return None, llm_result.usage if llm_result is not None else None
        try:
            return AnalystOutputPayload.model_validate(payload), llm_result.usage if llm_result is not None else None
        except Exception:
            return None, llm_result.usage if llm_result is not None else None

    def _build_fallback_analysis(
        self,
        *,
        task: AgentTask,
        entries: list[object],
        matches: list[object],
        key_files: list[str],
        workspace_root: Path,
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
            elif name in {"src", "domain", "config", "resources", "docs", "opencv", "imageprocess", "i18n"}:
                module_responsibilities[name] = self._describe_directory(name)
        project_type = self._infer_project_type(entries=entries, key_files=key_files)
        build_system = self._infer_build_system(entries=entries, workspace_root=workspace_root)
        return AnalystOutputPayload(
            project_summary=(
                f"{project_type}。"
                f" 顶层结构包含：{top_level_items}。"
                f" 构建方式：{build_system}。"
                f" 任务分析目标：{task.goal}。"
            ),
            module_responsibilities=module_responsibilities,
            entry_files=[path for path in key_files if path.endswith(("main.py", "agent.py", "runtime.py"))][:4],
            key_files=[
                AnalysisFilePayload(path=path, reason="与当前任务或系统主链路高度相关")
                for path in key_files[:5]
            ],
            coding_hints=[
                f"优先从这些目录理解系统结构：{', '.join(list(module_responsibilities)[:6])}" if module_responsibilities else "先从顶层目录识别模块边界。",
                f"优先确认构建链路：{build_system}",
                "优先复用现有 contract 与 runtime 基础设施。",
                "保持 v1/v2 边界清晰，避免把 v2 逻辑回灌到共享层或 v1。",
                *([f"优先关注：{', '.join(highlighted_files)}"] if highlighted_files else []),
            ],
        )

    def _infer_project_type(self, *, entries: list[object], key_files: list[str]) -> str:
        names = {str(entry.get("name")) for entry in entries if isinstance(entry, dict) and entry.get("name")}
        if "build.gradle.kts" in names or "settings.gradle.kts" in names:
            return "这是一个以 Gradle 为主构建的桌面或客户端项目"
        if "package.json" in names:
            return "这是一个前端或 Node.js 项目"
        if "pyproject.toml" in names:
            return "这是一个 Python 项目"
        if any(path.endswith("README.md") for path in key_files):
            return "这是一个包含文档和多个业务目录的应用项目"
        return "这是一个包含多个模块目录的应用项目"

    def _infer_build_system(self, *, entries: list[object], workspace_root: Path) -> str:
        names = {str(entry.get("name")) for entry in entries if isinstance(entry, dict) and entry.get("name")}
        build_parts: list[str] = []
        if "build.gradle.kts" in names or "settings.gradle.kts" in names:
            build_parts.append("Gradle")
        if "gradlew" in names:
            build_parts.append("Gradle Wrapper")
        if (workspace_root / "CMakeLists.txt").exists() or "opencv" in names:
            build_parts.append("可能包含 C++/OpenCV 原生构建")
        return " + ".join(build_parts) or "未识别出明确构建系统"

    def _describe_directory(self, name: str) -> str:
        mapping = {
            "src": "应用主要源码目录。",
            "domain": "领域模型与核心业务对象。",
            "config": "配置与环境相关定义。",
            "resources": "运行时资源文件。",
            "docs": "项目文档与说明材料。",
            "opencv": "与 OpenCV 或原生图像处理相关的集成代码。",
            "imageprocess": "图像处理模块或算法实现。",
            "i18n": "国际化文本与多语言资源。",
        }
        return mapping.get(name, "项目功能目录。")
