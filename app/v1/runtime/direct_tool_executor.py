"""规划步骤中的确定性工具执行。"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from time import monotonic
from uuid import uuid4

from app.contracts.message import ChatMessage
from app.contracts.planner import PlanStep
from app.contracts.run import RunChoice, RunMetrics, RunResult
from app.core.config import settings
from app.contracts.trace import TraceEvent
from app.trace.events import make_trace_event
from app.trace.recorder import JsonlTraceRecorder
from app.trace.repository import SQLiteTraceRepository
from app.v1.memory.repository import SQLiteMemoryRepository
from app.v1.memory.session_memory import SessionMemory
from app.v1.tools.registry import ToolRegistry
from app.v1.runtime.write_intent_parser import WriteIntentParser


class DirectToolExecutor:
    """为已知工具步骤提供 direct execution 能力。"""

    def __init__(self, write_intent_parser: WriteIntentParser | None = None) -> None:
        self.write_intent_parser = write_intent_parser or WriteIntentParser()

    def run_direct_plan_tool_step(
        self,
        *,
        session_id: str,
        model: str,
        reasoning_mode: str,
        tool_registry: ToolRegistry | None,
        session_memory: SessionMemory | None,
        step: PlanStep,
        previous_outputs: list[str],
        task: str,
        root_run_id: str,
        parent_run_id: str | None = None,
    ) -> RunResult | None:
        """当步骤工具和参数可确定时，直接执行工具而不依赖模型发起 tool call。"""
        if tool_registry is None or step.tool_name is None:
            return None

        arguments = self.infer_direct_tool_arguments(
            tool_name=step.tool_name,
            step=step,
            previous_outputs=previous_outputs,
            task=task,
            tool_registry=tool_registry,
        )
        if arguments is None:
            return None

        return self.run_direct_plan_tool_step_with_arguments(
            session_id=session_id,
            model=model,
            reasoning_mode=reasoning_mode,
            session_memory=session_memory,
            step=step,
            tool_registry=tool_registry,
            arguments=arguments,
            root_run_id=root_run_id,
            parent_run_id=parent_run_id,
        )

    def infer_direct_tool_arguments(
        self,
        *,
        tool_name: str,
        step: PlanStep,
        previous_outputs: list[str],
        task: str,
        tool_registry: ToolRegistry,
    ) -> dict[str, object] | None:
        """为确定性规划步骤推断直接执行所需的工具参数。"""
        if tool_name == "list_dir":
            return {"path": ".", "max_entries": 200}
        if tool_name == "read_file":
            candidate_path = self.infer_read_file_path(previous_outputs, tool_registry)
            if candidate_path is None:
                return None
            return {"path": candidate_path, "max_chars": 6000}
        if tool_name == "file_search":
            return self.infer_file_search_arguments(task, step)
        if tool_name == "write_file":
            return self.infer_write_file_arguments(previous_outputs)
        if tool_name == "retrieve_docs":
            query = (step.input_summary or task).strip()
            if not query:
                return None
            return {"query": query, "top_k": 3, "rerank": True}
        return None

    def infer_read_file_path(
        self,
        previous_outputs: list[str],
        tool_registry: ToolRegistry,
    ) -> str | None:
        """根据前序工具输出推断最值得读取的关键文件。"""
        common_candidates = [
            "package.json",
            "pyproject.toml",
            "settings.gradle.kts",
            "settings.gradle",
            "build.gradle.kts",
            "build.gradle",
            "pom.xml",
            "Cargo.toml",
            "CMakeLists.txt",
            "Makefile",
            "README.md",
        ]

        for output in reversed(previous_outputs):
            payload = self.write_intent_parser.parse_json_object(output)
            if not payload:
                continue
            entries = payload.get("entries")
            if not isinstance(entries, list):
                continue
            entry_names = {
                str(entry.get("name", "")): str(entry.get("path", ""))
                for entry in entries
                if isinstance(entry, dict)
            }
            for candidate in common_candidates:
                candidate_path = entry_names.get(candidate)
                if not candidate_path:
                    continue
                try:
                    resolved = Path(candidate_path).resolve().relative_to(tool_registry.workspace_root.resolve())
                    return str(resolved)
                except ValueError:
                    continue

        for candidate in common_candidates:
            candidate_path = tool_registry.workspace_root / candidate
            if candidate_path.exists() and candidate_path.is_file():
                return candidate
        return None

    def infer_file_search_arguments(self, task: str, step: PlanStep) -> dict[str, object] | None:
        """根据任务和步骤语义推断 file_search 参数。"""
        normalized = task.lower()
        if "todo" in normalized:
            return {"query": "TODO", "max_results": 20}
        if "函数" in task or "function" in normalized or "工具类" in task:
            return {"query": "def ", "glob": "**/*.py", "max_results": 20}
        if step.input_summary:
            summary = step.input_summary.strip()
            if summary:
                return {"query": summary, "max_results": 20}
        stripped = task.strip()
        if not stripped:
            return None
        return {"query": stripped, "max_results": 20}

    def infer_write_file_arguments(self, previous_outputs: list[str]) -> dict[str, object] | None:
        """从前序步骤结果中解析 write_file 所需的 path 和 content。"""
        for output in reversed(previous_outputs):
            parse_result = self.write_intent_parser.parse_write_file_arguments(output)
            if parse_result.arguments is not None:
                return parse_result.arguments
        return None

    def run_followup_direct_plan_tool_step(
        self,
        *,
        session_id: str,
        model: str,
        reasoning_mode: str,
        tool_registry: ToolRegistry | None,
        session_memory: SessionMemory | None,
        step: PlanStep,
        step_result: RunResult,
        root_run_id: str,
        parent_run_id: str | None = None,
    ) -> RunResult | None:
        """在 LLM 步骤输出了结构化工具参数时，补执行一次 direct tool。"""
        if tool_registry is None or step.tool_name != "write_file":
            return None
        parse_result = self.write_intent_parser.parse_write_file_arguments(step_result.final_output)
        if parse_result.arguments is None:
            return None
        return self.run_direct_plan_tool_step_with_arguments(
            session_id=session_id,
            model=model,
            reasoning_mode=reasoning_mode,
            session_memory=session_memory,
            step=step,
            tool_registry=tool_registry,
            arguments=parse_result.arguments,
            root_run_id=root_run_id,
            parent_run_id=parent_run_id,
        )

    def run_direct_plan_tool_step_with_arguments(
        self,
        *,
        session_id: str,
        model: str,
        reasoning_mode: str,
        session_memory: SessionMemory | None,
        step: PlanStep,
        tool_registry: ToolRegistry,
        arguments: dict[str, object],
        root_run_id: str,
        parent_run_id: str | None = None,
    ) -> RunResult:
        """使用已确定参数直接执行规划步骤工具。"""
        run_id = str(uuid4())
        started_at = monotonic()
        repository = session_memory.repository if session_memory is not None else SQLiteMemoryRepository()
        trace_repository = SQLiteTraceRepository(repository.db)
        trace_recorder = JsonlTraceRecorder(run_id=run_id)
        trace_events: list[TraceEvent] = []

        def append_event(event_type: str, message: str, payload: dict[str, object] | None = None) -> None:
            event = make_trace_event(
                run_id=run_id,
                root_run_id=root_run_id,
                parent_run_id=parent_run_id,
                session_id=session_id,
                event_type=event_type,
                message=message,
                payload=payload,
            )
            trace_events.append(event)
            trace_repository.save_event(run_id, event)
            trace_recorder.record(event)

        append_event("run_started", "Direct plan tool run started.", {"step_title": step.title, "tool_name": step.tool_name})
        append_event("step_started", "Direct tool step started.", {"step_title": step.title})
        validation_error = self._validate_direct_tool_arguments(
            tool_name=step.tool_name,
            arguments=arguments,
        )
        if validation_error is not None:
            append_event(
                "run_failed",
                "Direct plan tool validation failed.",
                {"step_title": step.title, "tool_name": step.tool_name, "error": validation_error},
            )
            result = RunResult(
                id=f"direct-plan-tool-{run_id}",
                model=model,
                reasoning_mode=reasoning_mode,
                choices=[
                    RunChoice(
                        index=0,
                        message=ChatMessage(role="assistant", content=validation_error),
                        finish_reason="stop",
                    )
                ],
                run_id=run_id,
                session_id=session_id,
                step_count=1,
                status="failed",
                final_output=validation_error,
                direct_tool_execution_used=True,
                metrics=RunMetrics(
                    duration_seconds=max(monotonic() - started_at, 0.0),
                    llm_call_count=0,
                    tool_call_count=0,
                    tool_error_count=0,
                    memory_write_count=0,
                    fallback_count=0,
                ),
                trace=trace_events,
            )
            if hasattr(repository, "save_run"):
                repository.save_run(
                    result,
                    f"[direct-tool] {step.title}",
                    is_top_level=False,
                    parent_run_id=parent_run_id or root_run_id,
                )
            if hasattr(repository, "save_trace_events"):
                repository.save_trace_events(run_id, trace_events)
            return result
        append_event("tool_called", "Tool called.", {"tool_name": step.tool_name, "arguments": arguments})
        tool_result = tool_registry.execute_tool(
            tool_name=step.tool_name,
            arguments=arguments,
            tool_call_id=f"direct-{run_id}",
        )
        append_event(
            "tool_result",
            "Tool result received.",
            {"tool_name": tool_result.name, "is_error": tool_result.is_error},
        )
        status = "failed" if tool_result.is_error else "completed"
        finish_event_type = "run_failed" if tool_result.is_error else "run_finished"
        finish_message = "Direct plan tool run failed." if tool_result.is_error else "Direct plan tool run finished."
        append_event(finish_event_type, finish_message, {"step_title": step.title, "tool_name": step.tool_name})

        result = RunResult(
            id=f"direct-plan-tool-{run_id}",
            model=model,
            reasoning_mode=reasoning_mode,
            choices=[
                RunChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=tool_result.content),
                    finish_reason="stop",
                )
            ],
            run_id=run_id,
            session_id=session_id,
            step_count=1,
            status=status,
            final_output=tool_result.content,
            direct_tool_execution_used=True,
            metrics=RunMetrics(
                duration_seconds=max(monotonic() - started_at, 0.0),
                llm_call_count=0,
                tool_call_count=1,
                tool_error_count=1 if tool_result.is_error else 0,
                memory_write_count=0,
                fallback_count=0,
            ),
            trace=trace_events,
        )
        if hasattr(repository, "save_run"):
            repository.save_run(
                result,
                f"[direct-tool] {step.title}",
                is_top_level=False,
                parent_run_id=parent_run_id or root_run_id,
            )
        if hasattr(repository, "save_trace_events"):
            repository.save_trace_events(run_id, trace_events)
        return result

    def normalize_write_candidate_result(self, result: RunResult) -> RunResult | None:
        """将可提取的 path/content 结果标准化为干净的结构化文本。"""
        parse_result = self.write_intent_parser.parse_write_file_arguments(result.final_output)
        if parse_result.arguments is None:
            return None
        normalized_output = json.dumps(
            {
                "path": parse_result.arguments["path"],
                "content": parse_result.arguments["content"],
            },
            ensure_ascii=False,
            indent=2,
        )
        updated_choices = result.choices
        if updated_choices:
            first_choice = updated_choices[0].model_copy(
                update={
                    "message": updated_choices[0].message.model_copy(
                        update={"content": normalized_output}
                    )
                }
            )
            updated_choices = [first_choice, *updated_choices[1:]]
        return result.model_copy(
            update={
                "final_output": normalized_output,
                "choices": updated_choices,
            }
        )

    def parse_write_candidate(self, text: str):
        """暴露统一的写入意图解析入口，供规划执行器复用。"""
        return self.write_intent_parser.parse_write_file_arguments(text)

    def _validate_direct_tool_arguments(
        self,
        *,
        tool_name: str | None,
        arguments: dict[str, object],
    ) -> str | None:
        """对 direct tool 执行参数做最小完整性校验。"""
        if tool_name != "write_file":
            return None
        path = arguments.get("path")
        content = arguments.get("content")
        if not isinstance(path, str) or not path.strip():
            return "生成了候选实现，但缺少可写入的目标路径，已停止落盘。"
        if not isinstance(content, str) or not content.strip():
            return "生成了候选实现，但文件内容为空，已停止落盘。"
        return self._validate_write_content(path=path.strip(), content=content)

    def _validate_write_content(self, *, path: str, content: str) -> str | None:
        """校验待写入内容是否明显截断。"""
        if settings.write_validation_mode == "permissive":
            return None

        stripped = content.rstrip()
        suffix = Path(path).suffix.lower()

        if stripped.count('"""') % 2 != 0 or stripped.count("'''") % 2 != 0:
            return "生成的文件内容疑似被截断：检测到未闭合的三引号字符串，已停止落盘。"

        suspicious_endings = (
            "Typical usage:",
            "Example:",
            "Examples:",
            "Usage:",
            "{",
            "[",
            "(",
            ",",
        )
        if any(stripped.endswith(ending) for ending in suspicious_endings):
            return "生成的文件内容疑似被截断：结尾不完整，已停止落盘。"

        if suffix == ".py":
            try:
                ast.parse(content)
            except SyntaxError as exc:
                return f"生成的 Python 内容未通过语法校验，已停止落盘：{exc.msg}"

        return None
