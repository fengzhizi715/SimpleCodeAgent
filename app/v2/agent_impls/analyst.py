"""Analyst agent implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

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
        mode = self._resolve_mode(task=task)
        previous_context = self._coerce_mapping(prompt_context.get("analysis_context"))

        tool_call_count = 0
        list_result = context.tool_registry.execute_tool(
            tool_name="list_dir",
            arguments={"path": ".", "max_entries": 50},
            tool_call_id=f"{task.task_id}-list-dir",
        )
        tool_call_count += 1
        list_payload = parse_tool_content(list_result.content)
        entries = list_payload.get("entries", [])
        repo_profile = self._detect_repo_profile(entries=entries, workspace_root=context.workspace_root)

        matches, search_call_count = self._search_relevant_files(
            mode=mode,
            task=task,
            context=context,
            workspace_root=context.workspace_root,
            repo_profile=repo_profile,
            previous_context=previous_context,
        )
        tool_call_count += search_call_count
        key_files = self._pick_key_files(
            mode=mode,
            entries=entries,
            matches=matches,
            workspace_root=context.workspace_root,
            repo_profile=repo_profile,
            previous_context=previous_context,
        )
        file_snippets, read_call_count = self._read_key_files(key_files=key_files, context=context, task=task)
        tool_call_count += read_call_count
        analysis_payload, usage = self._generate_analysis_with_llm(
            task=task,
            context=context,
            mode=mode,
            entries=entries,
            matches=matches,
            key_files=key_files,
            file_snippets=file_snippets,
            previous_context=previous_context,
        )
        metrics = RunMetrics(
            llm_call_count=1 if usage is not None else 0,
            tool_call_count=tool_call_count,
        )
        if analysis_payload is None:
            analysis_payload = self._build_fallback_analysis(
                task=task,
                mode=mode,
                entries=entries,
                matches=matches,
                key_files=key_files,
                workspace_root=context.workspace_root,
                repo_profile=repo_profile,
                previous_context=previous_context,
            )
            metrics.fallback_count += 1
        summary = analysis_payload.project_summary.strip()
        normalized_entry_files = [
            self._normalize_workspace_path(path=path, workspace_root=context.workspace_root)
            for path in analysis_payload.entry_files
            if self._normalize_workspace_path(path=path, workspace_root=context.workspace_root)
        ]
        normalized_key_files = self._normalize_key_file_payloads(
            key_files=analysis_payload.key_files,
            workspace_root=context.workspace_root,
        )
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
                "entry_files": normalized_entry_files,
                "key_files": normalized_key_files,
                "coding_hints": analysis_payload.coding_hints,
                "root_entries": entries,
                "highlighted_files": matches[:5],
                "analysis_mode": mode,
            },
            artifacts=[
                AgentArtifact(
                    key="project_summary",
                    type="analysis",
                    summary="项目结构分析完成",
                    content={
                        "project_summary": summary,
                        "module_responsibilities": analysis_payload.module_responsibilities,
                        "entry_files": normalized_entry_files,
                        "key_files": normalized_key_files,
                        "coding_hints": analysis_payload.coding_hints,
                        "analysis_mode": mode,
                    },
                )
            ],
        )

    def _resolve_mode(self, *, task: AgentTask) -> Literal["directory_scan", "key_file_read", "summary"]:
        explicit_mode = str(task.input_data.get("analysis_mode") or "").strip().lower()
        if explicit_mode in {"directory_scan", "key_file_read", "summary"}:
            return explicit_mode  # type: ignore[return-value]
        tool_name = str(task.input_data.get("tool_name") or "").strip().lower()
        goal = task.goal.strip().lower()
        title = str(task.input_data.get("step_title") or "").strip().lower()
        haystack = " ".join(part for part in [tool_name, goal, title] if part)
        if any(token in haystack for token in ("总结", "汇总", "概述", "summary", "summar", "final")):
            return "summary"
        if any(token in haystack for token in ("read_file", "关键文件", "配置文件", "入口文件", "模块职责", "源码")):
            return "key_file_read"
        return "directory_scan"

    def _coerce_mapping(self, value: object) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    def _normalize_workspace_path(self, *, path: str, workspace_root: Path) -> str:
        raw = path.strip()
        if not raw:
            return ""
        candidate = Path(raw)
        if candidate.is_absolute():
            return relative_path(workspace_root, candidate)
        return raw

    def _normalize_key_file_payloads(
        self,
        *,
        key_files: list[AnalysisFilePayload],
        workspace_root: Path,
    ) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in key_files:
            path = self._normalize_workspace_path(path=item.path, workspace_root=workspace_root)
            if not path or path in seen:
                continue
            seen.add(path)
            normalized.append({"path": path, "reason": item.reason})
        return normalized

    def _detect_repo_profile(self, *, entries: list[object], workspace_root: Path) -> Literal["gradle_kotlin", "python", "node", "generic"]:
        names = {str(entry.get("name")) for entry in entries if isinstance(entry, dict) and entry.get("name")}
        if {"build.gradle.kts", "settings.gradle.kts"} & names or "gradlew" in names or (workspace_root / "src").exists():
            return "gradle_kotlin"
        if "pyproject.toml" in names or (workspace_root / "app").exists():
            return "python"
        if "package.json" in names:
            return "node"
        return "generic"

    def _search_relevant_files(
        self,
        *,
        mode: Literal["directory_scan", "key_file_read", "summary"],
        task: AgentTask,
        context: AgentContext,
        workspace_root: Path,
        repo_profile: Literal["gradle_kotlin", "python", "node", "generic"],
        previous_context: dict[str, Any],
    ) -> tuple[list[object], int]:
        if mode == "directory_scan":
            return [], 0
        if mode == "summary":
            previous_key_files = previous_context.get("key_files")
            if isinstance(previous_key_files, list) and previous_key_files:
                return previous_key_files[:8], 0
        query, glob = self._build_search_query(task=task, repo_profile=repo_profile, workspace_root=workspace_root)
        if not query or not glob:
            return [], 0
        result = context.tool_registry.execute_tool(
            tool_name="file_search",
            arguments={"query": query, "glob": glob, "max_results": 12},
            tool_call_id=f"{task.task_id}-file-search",
        )
        payload = parse_tool_content(result.content)
        return payload.get("matches", []), 1

    def _build_search_query(
        self,
        *,
        task: AgentTask,
        repo_profile: Literal["gradle_kotlin", "python", "node", "generic"],
        workspace_root: Path,
    ) -> tuple[str, str]:
        if repo_profile == "gradle_kotlin":
            if (workspace_root / "src").exists():
                return "fun ", "src/**/*.kt"
            if (workspace_root / "domain").exists():
                return "class ", "domain/**/*.kt"
            return "plugin", "*.gradle.kts"
        if repo_profile == "python":
            return "class ", "app/**/*.py"
        if repo_profile == "node":
            return "export ", "src/**/*.{ts,tsx,js,jsx}"
        query = str(task.input_data.get("tool_name") or "").strip() or "class "
        return query, "**/*"

    def _pick_key_files(
        self,
        *,
        mode: Literal["directory_scan", "key_file_read", "summary"],
        entries: list[object],
        matches: list[object],
        workspace_root: Path,
        repo_profile: Literal["gradle_kotlin", "python", "node", "generic"],
        previous_context: dict[str, Any],
    ) -> list[str]:
        selected: list[str] = []
        preferred = self._preferred_files_for_profile(repo_profile=repo_profile)
        for candidate in preferred:
            if (workspace_root / candidate).exists():
                selected.append(candidate)
        if mode in {"key_file_read", "summary"}:
            for item in previous_context.get("key_files", []):
                if not isinstance(item, dict):
                    continue
                path = self._normalize_workspace_path(
                    path=str(item.get("path") or "").strip(),
                    workspace_root=workspace_root,
                )
                if path and (workspace_root / path).exists() and path not in selected:
                    selected.append(path)
        for match in matches:
            if not isinstance(match, dict):
                continue
            match_path = str(match.get("path") or match.get("name") or "")
            if not match_path:
                continue
            candidate_path = Path(match_path)
            relative = (
                self._normalize_workspace_path(path=match_path, workspace_root=workspace_root)
                if candidate_path.is_absolute()
                else match_path
            )
            absolute = workspace_root / relative
            if absolute.is_dir():
                for nested in self._discover_files_in_directory(absolute=absolute, workspace_root=workspace_root):
                    if nested not in selected:
                        selected.append(nested)
                    if len(selected) >= 6:
                        break
                continue
            if relative not in selected:
                selected.append(relative)
            if len(selected) >= 6:
                break
        return selected[:6]

    def _preferred_files_for_profile(
        self,
        *,
        repo_profile: Literal["gradle_kotlin", "python", "node", "generic"],
    ) -> list[str]:
        if repo_profile == "gradle_kotlin":
            return [
                "README.md",
                "README-EN.md",
                "settings.gradle.kts",
                "build.gradle.kts",
                "gradle.properties",
                "compose-desktop.pro",
            ]
        if repo_profile == "python":
            return [
                "README.md",
                "pyproject.toml",
                "app/main.py",
                "app/api/routes/agent.py",
                "app/v1/runtime/loop.py",
                "app/v2/runtime.py",
            ]
        if repo_profile == "node":
            return ["README.md", "package.json", "src/main.ts", "src/index.ts", "vite.config.ts"]
        return ["README.md", "README-EN.md"]

    def _discover_files_in_directory(self, *, absolute: Path, workspace_root: Path) -> list[str]:
        discovered: list[str] = []
        if not absolute.exists() or not absolute.is_dir():
            return discovered
        for path in absolute.rglob("*"):
            if not path.is_file():
                continue
            discovered.append(relative_path(workspace_root, path))
            if len(discovered) >= 3:
                break
        return discovered

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
        mode: Literal["directory_scan", "key_file_read", "summary"],
        entries: list[object],
        matches: list[object],
        key_files: list[str],
        file_snippets: dict[str, str],
        previous_context: dict[str, Any],
    ) -> tuple[AnalystOutputPayload | None, RunUsage | None]:
        system_prompt = (
            "You are the Analyst Agent for SimpleCodeAgent V2. "
            "Return only valid JSON with keys: project_summary, module_responsibilities, "
            "entry_files, key_files, coding_hints. "
            "module_responsibilities must be an object. key_files must be a list of {path, reason}. "
            "Keep the output concise and grounded in the provided repository observations. "
            "Respect the requested analysis mode: directory_scan should focus on structure, "
            "key_file_read should focus on meaningful config/entry/source files, "
            "summary should synthesize existing findings instead of repeating raw listings."
        )
        user_prompt = "\n".join(
            [
                f"分析模式：{mode}",
                f"任务目标：{task.goal}",
                f"根目录条目：{json.dumps(entries[:20], ensure_ascii=False)}",
                f"搜索命中：{json.dumps(matches[:8], ensure_ascii=False)}",
                f"关键文件：{json.dumps(key_files, ensure_ascii=False)}",
                f"文件片段：{json.dumps(file_snippets, ensure_ascii=False)}",
                f"已有分析上下文：{json.dumps(previous_context, ensure_ascii=False)}",
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
        mode: Literal["directory_scan", "key_file_read", "summary"],
        entries: list[object],
        matches: list[object],
        key_files: list[str],
        workspace_root: Path,
        repo_profile: Literal["gradle_kotlin", "python", "node", "generic"],
        previous_context: dict[str, Any],
    ) -> AnalystOutputPayload:
        top_level_items = ", ".join(
            entry["name"] for entry in entries if isinstance(entry, dict) and entry.get("name")
        ) or "无"
        highlighted_files = [
            self._normalize_workspace_path(
                path=str(match.get("path") or match.get("name") or ""),
                workspace_root=workspace_root,
            )
            for match in matches[:5]
            if isinstance(match, dict) and (match.get("path") or match.get("name"))
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
        previous_summary = str(previous_context.get("project_summary") or "").strip()
        summary_prefix = {
            "directory_scan": "本阶段先识别目录结构与模块边界。",
            "key_file_read": "本阶段聚焦关键配置和入口文件。",
            "summary": "本阶段根据前序目录观察和关键文件信息收敛总结。",
        }[mode]
        if repo_profile == "gradle_kotlin":
            preferred_entries = [name for name in ["src", "domain", "config", "resources", "docs"] if (workspace_root / name).exists()]
            if preferred_entries:
                module_responsibilities.setdefault("build", "Gradle Kotlin DSL 负责项目构建和模块装配。")
                highlighted_files = [path for path in key_files if path.endswith((".kts", ".md"))][:5] or highlighted_files
        summary_parts = [summary_prefix]
        if mode == "directory_scan":
            summary_parts.extend(
                [
                    f"{project_type}。",
                    f"顶层结构包含：{top_level_items}。",
                    f"构建方式：{build_system}。",
                    f"任务分析目标：{task.goal}。",
                ]
            )
        elif mode == "key_file_read":
            summary_parts.extend(
                [
                    f"{project_type}。",
                    f"构建方式：{build_system}。",
                    f"当前重点文件：{', '.join(key_files[:4]) if key_files else '无'}。",
                ]
            )
        else:
            if previous_summary:
                summary_parts.append(f"前序分析结论：{previous_summary}")
            summary_parts.extend(
                [
                    f"{project_type}。",
                    f"构建方式：{build_system}。",
                    "综合目录和关键文件后，可进一步围绕构建脚本、主入口与核心业务目录理解系统结构。",
                ]
            )
        return AnalystOutputPayload(
            project_summary=" ".join(part for part in summary_parts if part),
            module_responsibilities=module_responsibilities,
            entry_files=self._pick_entry_files(key_files=key_files, repo_profile=repo_profile),
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

    def _pick_entry_files(
        self,
        *,
        key_files: list[str],
        repo_profile: Literal["gradle_kotlin", "python", "node", "generic"],
    ) -> list[str]:
        suffixes: tuple[str, ...]
        if repo_profile == "gradle_kotlin":
            suffixes = (".kts", "Main.kt", "App.kt")
        elif repo_profile == "python":
            suffixes = ("main.py", "agent.py", "runtime.py")
        elif repo_profile == "node":
            suffixes = ("main.ts", "index.ts", "main.js", "index.js")
        else:
            suffixes = ("README.md",)
        return [path for path in key_files if path.endswith(suffixes)][:4]

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
