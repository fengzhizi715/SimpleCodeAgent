"""规划步骤执行器。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4

from app.contracts.message import ChatMessage
from app.contracts.planner import PlanStep
from app.contracts.run import RunChoice, RunMetrics, RunResult, RunUsage
from app.llm.client import LLMProvider
from app.v1.memory.session_memory import SessionMemory
from app.v1.memory.summary_memory import SummaryMemory
from app.v1.planner.base import Planner
from app.v1.runtime.direct_tool_executor import DirectToolExecutor
from app.v1.tools.registry import ToolRegistry
from app.trace.events import make_trace_event


@dataclass
class WriteFileOutcome:
    """记录规划执行中 write_file 的真实落盘结果。"""

    attempted: bool = False
    attempted_paths: list[str] | None = None
    confirmed_paths: list[str] | None = None

    def __post_init__(self) -> None:
        if self.attempted_paths is None:
            self.attempted_paths = []
        if self.confirmed_paths is None:
            self.confirmed_paths = []

    @property
    def all_succeeded(self) -> bool:
        """只有所有尝试写入的路径都确认存在，才视为全部成功。"""
        if not self.attempted:
            return True
        attempted_set = {path for path in self.attempted_paths if path}
        confirmed_set = {path for path in self.confirmed_paths if path}
        return bool(attempted_set) and attempted_set.issubset(confirmed_set)

    @property
    def unconfirmed_paths(self) -> list[str]:
        """返回未能确认成功落盘的路径。"""
        attempted_set = {path for path in self.attempted_paths if path}
        confirmed_set = {path for path in self.confirmed_paths if path}
        return sorted(attempted_set - confirmed_set)


class PlanExecutor:
    """负责规划步骤的顺序执行和汇总。"""

    def __init__(
        self,
        *,
        run_callable: Callable[..., RunResult],
        direct_tool_executor: DirectToolExecutor,
    ) -> None:
        self.run_callable = run_callable
        self.direct_tool_executor = direct_tool_executor

    def run_with_plan(
        self,
        *,
        provider: LLMProvider,
        model: str,
        task: str,
        system_prompt: str,
        session_id: str,
        reasoning_mode: str = "default",
        temperature: float = 0.0,
        max_steps: int = 3,
        run_timeout_seconds: int = 120,
        tool_registry: ToolRegistry | None = None,
        session_memory: SessionMemory | None = None,
        summary_memory: SummaryMemory | None = None,
        planner: Planner,
        root_run_id: str | None = None,
    ) -> RunResult:
        """先规划，再顺序执行步骤并汇总结果。"""
        effective_root_run_id = root_run_id or str(uuid4())
        plan = planner.create_plan(task)
        if not plan:
            return self.run_callable(
                provider=provider,
                model=model,
                task=task,
                system_prompt=system_prompt,
                session_id=session_id,
                reasoning_mode=reasoning_mode,
                temperature=temperature,
                max_steps=max_steps,
                run_timeout_seconds=run_timeout_seconds,
                tool_registry=tool_registry,
                session_memory=session_memory,
                summary_memory=summary_memory,
                root_run_id=effective_root_run_id,
            )

        step_outputs: list[str] = []
        step_results: list[RunResult] = []
        total_step_count = 0
        plan_failed = False
        direct_tool_execution_used = False

        index = 0
        while index < len(plan):
            step = plan[index]
            step_result, updated_step = self._run_plan_step(
                provider=provider,
                model=model,
                task=task,
                system_prompt=system_prompt,
                session_id=session_id,
                reasoning_mode=reasoning_mode,
                temperature=temperature,
                max_steps=max_steps,
                run_timeout_seconds=run_timeout_seconds,
                tool_registry=tool_registry,
                session_memory=session_memory,
                summary_memory=summary_memory,
                step=step,
                step_index=index + 1,
                total_steps=len(plan),
                previous_outputs=step_outputs,
                root_run_id=effective_root_run_id,
            )
            # Replace original step with updated copy (avoid in-place mutation)
            plan[index] = updated_step
            step_outputs.append(step_result.final_output)
            step_results.append(step_result)
            total_step_count += step_result.step_count
            if step_result.direct_tool_execution_used:
                direct_tool_execution_used = True
            if updated_step.status == "failed":
                plan_failed = True
                break
            if index + 1 < len(plan):
                next_step = plan[index + 1]
                skipped_result, updated_next_step = self._run_skip_llm_write_step(
                    session_id=session_id,
                    model=model,
                    reasoning_mode=reasoning_mode,
                    tool_registry=tool_registry,
                    session_memory=session_memory,
                    source_result=step_result,
                    write_step=next_step,
                    root_run_id=effective_root_run_id,
                )
                if skipped_result is not None:
                    # Replace original next_step with updated copy
                    plan[index + 1] = updated_next_step
                    step_outputs.append(skipped_result.final_output)
                    step_results.append(skipped_result)
                    total_step_count += skipped_result.step_count
                    if skipped_result.direct_tool_execution_used:
                        direct_tool_execution_used = True
                    if updated_next_step.status == "failed":
                        plan_failed = True
                    index += 2
                    if plan_failed:
                        break
                    continue
            index += 1

        executed_steps = plan[:len(step_results)]
        expected_tool_usage = any(step.tool_name for step in executed_steps)
        actual_tool_usage = self._has_tool_execution(step_results)
        aggregated_usage = self._merge_usage([step_result.usage for step_result in step_results])
        aggregated_metrics = self._merge_metrics([step_result.metrics for step_result in step_results])
        write_outcome = self._assess_write_file_outcome(executed_steps, step_results)
        expected_write_execution = any(step.tool_name == "write_file" for step in executed_steps)

        if expected_tool_usage and not actual_tool_usage:
            for i, step in enumerate(executed_steps):
                if step.tool_name and step.status == "completed":
                    updated = step.model_copy(update={
                        "status": "failed",
                        "output_summary": "分析未实际执行工具；模型输出了文本结果，但没有发起真实 tool call。",
                    })
                    executed_steps[i] = updated
                    plan[i] = updated
                    break
            failure_message = "分析未实际执行工具，无法可靠汇总结果。请检查模型是否发起了真实 tool call。"
            return self._build_failed_plan_result(
                model=model,
                reasoning_mode=reasoning_mode,
                session_id=session_id,
                total_step_count=total_step_count,
                plan=plan,
                usage=aggregated_usage,
                metrics=aggregated_metrics,
                direct_tool_execution_used=direct_tool_execution_used,
                message=failure_message,
                run_id=step_results[-1].run_id if step_results else None,
            )

        if plan_failed:
            failure_message = self._build_plan_failure_message(executed_steps, step_results)
            return self._build_failed_plan_result(
                model=model,
                reasoning_mode=reasoning_mode,
                session_id=session_id,
                total_step_count=total_step_count,
                plan=plan,
                usage=aggregated_usage,
                metrics=aggregated_metrics,
                direct_tool_execution_used=direct_tool_execution_used,
                message=failure_message,
                run_id=step_results[-1].run_id if step_results else None,
            )

        if expected_write_execution and not write_outcome.all_succeeded:
            failure_message = self._build_write_file_failure_message(write_outcome)
            for i, (step, step_result) in enumerate(zip(executed_steps, step_results)):
                if step.tool_name != "write_file":
                    continue
                if not self._is_confirmed_write_result(step_result):
                    updated = step.model_copy(update={
                        "status": "failed",
                        "output_summary": failure_message,
                    })
                    executed_steps[i] = updated
                    plan[i] = updated
                    break
            return self._build_failed_plan_result(
                model=model,
                reasoning_mode=reasoning_mode,
                session_id=session_id,
                total_step_count=total_step_count,
                plan=plan,
                usage=aggregated_usage,
                metrics=aggregated_metrics,
                direct_tool_execution_used=direct_tool_execution_used,
                message=failure_message,
                run_id=step_results[-1].run_id if step_results else None,
            )

        summary_prompt = self._build_summary_prompt(
            task=task,
            plan=plan,
            step_outputs=step_outputs,
            write_outcome=write_outcome,
        )
        summary_result = self.run_callable(
            provider=provider,
            model=model,
            task=summary_prompt,
            system_prompt=system_prompt,
            session_id=session_id,
            reasoning_mode=reasoning_mode,
            temperature=temperature,
            max_steps=max_steps,
            run_timeout_seconds=run_timeout_seconds,
            tool_registry=self._build_runtime_tool_registry(
                tool_registry=tool_registry,
                disable_tools=True,
            ),
            session_memory=session_memory,
            summary_memory=summary_memory,
            persist_session_memory=False,
            root_run_id=effective_root_run_id,
            parent_run_id=effective_root_run_id,
            is_top_level=False,
        )
        if session_memory is not None and self._is_success_status(summary_result.status):
            session_memory.append(
                session_id,
                [
                    ChatMessage(role="user", content=task),
                    ChatMessage(role="assistant", content=summary_result.final_output),
                ],
            )
            if summary_result.metrics is not None:
                summary_result.metrics.memory_write_count += 1
        aggregated_metrics = self._merge_metrics(
            [step_result.metrics for step_result in step_results] + [summary_result.metrics]
        )
        return summary_result.model_copy(
            update={
                "session_id": session_id,
                "step_count": total_step_count + summary_result.step_count,
                "plan": plan,
                "status": "failed" if plan_failed else summary_result.status,
                "usage": self._merge_usage([step_result.usage for step_result in step_results] + [summary_result.usage]),
                "metrics": aggregated_metrics,
                "direct_tool_execution_used": direct_tool_execution_used,
            }
        )

    def _run_skip_llm_write_step(
        self,
        *,
        session_id: str,
        model: str,
        reasoning_mode: str,
        tool_registry: ToolRegistry | None,
        session_memory: SessionMemory | None,
        source_result: RunResult,
        write_step: PlanStep,
        root_run_id: str,
    ) -> tuple[RunResult | None, PlanStep | None]:
        """当上一阶段已产出 path/content 时，直接执行 write_file，跳过额外的 LLM 一跳。

        Returns:
            (RunResult | None, PlanStep | None) 元组。当步骤不适用时返回 (None, None)。
            返回的 PlanStep 是更新后的副本，原始 step 不会被原地修改。
        """
        if tool_registry is None or write_step.tool_name != "write_file":
            return None, None
        parse_result = self.direct_tool_executor.parse_write_candidate(source_result.final_output)
        if parse_result.arguments is None:
            updated_step = write_step.model_copy(update={
                "status": "failed",
                "output_summary": (
                    "无法从上一步结果中提取 write_file 所需参数："
                    f"{parse_result.error or '未知原因'}"
                ),
            })
            failed_run_id = str(uuid4())
            return RunResult(
                id=f"planner-write-parse-failed-{failed_run_id}",
                model=model,
                reasoning_mode=reasoning_mode,
                choices=[
                    RunChoice(
                        index=0,
                        message=ChatMessage(role="assistant", content=updated_step.output_summary),
                        finish_reason="stop",
                    )
                ],
                run_id=failed_run_id,
                session_id=session_id,
                step_count=1,
                status="failed",
                final_output=updated_step.output_summary,
                direct_tool_execution_used=False,
                metrics=RunMetrics(),
                trace=[
                    make_trace_event(
                        run_id=failed_run_id,
                        root_run_id=root_run_id,
                        parent_run_id=root_run_id,
                        session_id=session_id,
                        event_type="run_failed",
                        message="Write intent parsing failed before direct write step.",
                        payload={
                            "step_title": updated_step.title,
                            "tool_name": updated_step.tool_name,
                            "parser_error": parse_result.error or "unknown",
                            "format_hint": parse_result.format_hint or "unknown",
                        },
                    )
                ],
            ), updated_step
        # Create a working copy for in-progress status
        working_step = write_step.model_copy(update={"status": "in_progress"})
        result = self.direct_tool_executor.run_direct_plan_tool_step_with_arguments(
            session_id=session_id,
            model=model,
            reasoning_mode=reasoning_mode,
            session_memory=session_memory,
            step=working_step,
            tool_registry=tool_registry,
            arguments=parse_result.arguments,
            root_run_id=root_run_id,
            parent_run_id=root_run_id,
        )
        updated_step = working_step.model_copy(update={
            "output_summary": result.final_output,
            "status": "completed" if result.status == "completed" else "failed",
        })
        return result, updated_step

    def _run_plan_step(
        self,
        *,
        provider: LLMProvider,
        model: str,
        task: str,
        system_prompt: str,
        session_id: str,
        reasoning_mode: str,
        temperature: float,
        max_steps: int,
        run_timeout_seconds: int,
        tool_registry: ToolRegistry | None,
        session_memory: SessionMemory | None,
        summary_memory: SummaryMemory | None,
        step: PlanStep,
        step_index: int,
        total_steps: int,
        previous_outputs: list[str],
        root_run_id: str,
    ) -> tuple[RunResult, PlanStep]:
        """执行单个规划步骤，并按需要重试。

        Returns:
            (RunResult, PlanStep) 元组。返回的 PlanStep 是更新后的副本，原始 step 不会被原地修改。
        """
        last_result: RunResult | None = None
        # Create a working copy to avoid mutating the original step
        working_step = step.model_copy()
        total_attempts = max(1, working_step.max_retries + 1)

        for attempt_index in range(total_attempts):
            working_step = working_step.model_copy(update={
                "status": "in_progress",
                "retry_count": attempt_index,
            })
            direct_result = self.direct_tool_executor.run_direct_plan_tool_step(
                session_id=session_id,
                model=model,
                reasoning_mode=reasoning_mode,
                tool_registry=tool_registry,
                session_memory=session_memory,
                step=working_step,
                previous_outputs=previous_outputs,
                task=task,
                root_run_id=root_run_id,
                parent_run_id=root_run_id,
            )
            if direct_result is not None:
                last_result = direct_result
                working_step = working_step.model_copy(update={"output_summary": direct_result.final_output})
                if self._is_success_status(direct_result.status):
                    working_step = working_step.model_copy(update={"status": "completed"})
                    return direct_result, working_step
                continue

            step_prompt = self._build_step_prompt(
                task=task,
                step=working_step,
                step_index=step_index,
                total_steps=total_steps,
                previous_outputs=previous_outputs,
            )
            last_result = self.run_callable(
                provider=provider,
                model=model,
                task=step_prompt,
                system_prompt=system_prompt,
                session_id=session_id,
                reasoning_mode=reasoning_mode,
                temperature=temperature,
                max_steps=max_steps,
                run_timeout_seconds=run_timeout_seconds,
                tool_registry=self._build_runtime_tool_registry(
                    tool_registry=tool_registry,
                    disable_tools=self._is_summary_step(working_step),
                ),
                session_memory=session_memory,
                summary_memory=summary_memory,
                persist_session_memory=False,
                root_run_id=root_run_id,
                parent_run_id=root_run_id,
                is_top_level=False,
            )
            normalized_write_candidate = self.direct_tool_executor.normalize_write_candidate_result(last_result)
            if normalized_write_candidate is not None:
                last_result = normalized_write_candidate
            followup_direct_result = self.direct_tool_executor.run_followup_direct_plan_tool_step(
                session_id=session_id,
                model=model,
                reasoning_mode=reasoning_mode,
                tool_registry=tool_registry,
                session_memory=session_memory,
                step=working_step,
                step_result=last_result,
                root_run_id=root_run_id,
                parent_run_id=root_run_id,
            )
            if followup_direct_result is not None:
                last_result = followup_direct_result
            working_step = working_step.model_copy(update={"output_summary": last_result.final_output})
            if self._is_success_status(last_result.status):
                working_step = working_step.model_copy(update={"status": "completed"})
                return last_result, working_step

        working_step = working_step.model_copy(update={"status": "failed"})
        return last_result or RunResult(
            id="planner-step-fallback",
            model=model,
            reasoning_mode=reasoning_mode,
            choices=[],
            session_id=session_id,
            status="failed",
            final_output=f"步骤执行失败：{working_step.title}",
        ), working_step

    def _build_step_prompt(
        self,
        *,
        task: str,
        step: PlanStep,
        step_index: int,
        total_steps: int,
        previous_outputs: list[str],
    ) -> str:
        """构造单个规划步骤的执行提示。"""
        is_summary_step = "总结" in step.title or "总结" in step.description
        sections = [
            f"总任务：{task}",
            f"当前是第 {step_index}/{total_steps} 步。",
            f"步骤标题：{step.title}",
            f"步骤描述：{step.description}",
        ]
        if step.input_summary:
            sections.append(f"输入摘要：{step.input_summary}")
        if step.tool_name:
            sections.extend(
                [
                    f"本步骤优先使用工具：{step.tool_name}",
                    "如果需要获取真实信息，请直接发起真实 tool call，不要只描述计划，也不要输出伪 JSON、伪命令块或示例参数。",
                    "只有在拿到工具结果后，再基于结果输出当前步骤结论。",
                ]
            )
        if previous_outputs:
            sections.append("前序步骤结果：")
            sections.extend(
                [f"- 第 {index + 1} 步：{output}" for index, output in enumerate(previous_outputs)]
            )
        if is_summary_step:
            sections.extend(
                [
                    "本步骤是收口总结步骤，必须只基于现有前序步骤结果直接给出结论。",
                    "不要继续规划下一步，不要要求再读取 README、配置文件或其他文件，不要说“需要再获取更多信息”。",
                    "如果现有信息足够，就直接输出结构化总结。",
                    "如果现有信息有限，也要先给出当前可得结论，并明确说明哪些判断是基于已有结果的推断。",
                ]
            )
        sections.append("请只完成当前步骤，并输出该步骤的结果。")
        return "\n".join(sections)

    def _build_summary_prompt(
        self,
        *,
        task: str,
        plan: list[PlanStep],
        step_outputs: list[str],
        write_outcome: WriteFileOutcome,
    ) -> str:
        """构造最终汇总提示。"""
        lines = [f"请基于以下步骤结果，汇总完成总任务：{task}", "步骤结果："]
        for index, step in enumerate(plan, start=1):
            lines.append(f"{index}. {step.title}")
            if step.status == "failed":
                lines.append(f"步骤失败：{step.output_summary or '无输出'}")
                continue
            if index <= len(step_outputs):
                lines.append(step_outputs[index - 1])
        if write_outcome.attempted:
            if write_outcome.confirmed_paths:
                lines.append("已确认成功写入的文件：")
                lines.extend([f"- {path}" for path in write_outcome.confirmed_paths])
            if write_outcome.unconfirmed_paths:
                lines.append("未确认成功落盘的文件：")
                lines.extend([f"- {path}" for path in write_outcome.unconfirmed_paths])
        lines.extend(
            [
                "请直接基于以上步骤结果输出最终答案。",
                "不要继续规划下一步，不要要求再读取 README、配置文件或其他文件，不要输出“我们将继续……”之类的话。",
                "如果信息已经足够，请直接完成总结。",
                "如果信息仍然有限，请基于现有结果先给出可靠结论，并明确标注哪些是推断。",
            ]
        )
        if write_outcome.attempted:
            lines.extend(
                [
                    "涉及 write_file 时，只有在“已确认成功写入的文件”列表中的路径，才允许表述为“已完成写入”或“已成功落盘”。",
                    "对于未确认成功落盘的路径，必须明确表述为“仅生成了候选实现，未成功落盘”。",
                ]
            )
        return "\n".join(lines)

    def _merge_metrics(self, metrics_list: list[RunMetrics | None]) -> RunMetrics:
        """合并多次运行结果的指标，用于 planner 汇总场景。"""
        merged = RunMetrics()
        for metrics in metrics_list:
            if metrics is None:
                continue
            merged.duration_seconds += metrics.duration_seconds
            merged.llm_call_count += metrics.llm_call_count
            merged.tool_call_count += metrics.tool_call_count
            merged.tool_error_count += metrics.tool_error_count
            merged.memory_write_count += metrics.memory_write_count
            merged.fallback_count += metrics.fallback_count
        return merged

    def _merge_usage(self, usage_list: list[RunUsage | None]) -> RunUsage | None:
        """合并多次运行的 token usage，用于 planner 汇总场景。"""
        merged = RunUsage()
        has_usage = False
        for usage in usage_list:
            if usage is None:
                continue
            has_usage = True
            merged.prompt_tokens += usage.prompt_tokens
            merged.completion_tokens += usage.completion_tokens
            merged.total_tokens += usage.total_tokens
        return merged if has_usage else None

    def _has_tool_execution(self, step_results: list[RunResult]) -> bool:
        """判断规划步骤是否真的发起过工具调用。"""
        for result in step_results:
            if result.metrics is not None and result.metrics.tool_call_count > 0:
                return True
            if any(event.event_type == "tool_called" for event in result.trace):
                return True
        return False

    def _is_success_status(self, status: str | None) -> bool:
        """判断运行结果是否可视为成功完成或可继续汇总。"""
        return status in {"completed", "partial_completed"}

    def _is_summary_step(self, step: PlanStep) -> bool:
        """判断当前步骤是否是收口总结类步骤。"""
        return "总结" in step.title or "总结" in step.description

    def _build_runtime_tool_registry(
        self,
        *,
        tool_registry: ToolRegistry | None,
        disable_tools: bool,
    ) -> ToolRegistry | None:
        """按步骤语义裁剪运行时可见工具。"""
        if not disable_tools:
            return tool_registry
        workspace_root = tool_registry.workspace_root if tool_registry is not None else None
        return ToolRegistry(workspace_root=workspace_root)

    def _assess_write_file_outcome(
        self,
        plan: list[PlanStep],
        step_results: list[RunResult],
    ) -> WriteFileOutcome:
        """检查 write_file 是否真的成功执行并落盘。"""
        outcome = WriteFileOutcome()
        for step, result in zip(plan, step_results):
            if step.tool_name != "write_file":
                continue
            outcome.attempted = True
            attempted_path = self._extract_write_path(result)
            if attempted_path is not None and attempted_path not in outcome.attempted_paths:
                outcome.attempted_paths.append(attempted_path)
            if self._is_confirmed_write_result(result):
                confirmed_path = self._extract_write_path(result)
                if confirmed_path is not None and confirmed_path not in outcome.confirmed_paths:
                    outcome.confirmed_paths.append(confirmed_path)
        return outcome

    def _extract_write_payload(self, result: RunResult) -> dict[str, object] | None:
        """从 write_file 步骤结果中提取结构化 payload。"""
        if not result.final_output:
            return None
        return self.direct_tool_executor.write_intent_parser.extract_json_object(result.final_output)

    def _extract_write_path(self, result: RunResult) -> str | None:
        """提取 write_file 结果中的目标路径。"""
        payload = self._extract_write_payload(result)
        if not payload:
            return None
        path = payload.get("path")
        if isinstance(path, str) and path.strip():
            return path.strip()
        return None

    def _is_confirmed_write_result(self, result: RunResult) -> bool:
        """只有 write_file 返回成功且目标文件存在时，才视为真正写入成功。"""
        if result.status != "completed":
            return False
        payload = self._extract_write_payload(result)
        if not payload:
            return False
        if payload.get("ok") is not True or payload.get("dry_run") is True:
            return False
        path = payload.get("path")
        if not isinstance(path, str) or not path.strip():
            return False
        try:
            return Path(path).expanduser().resolve().is_file()
        except OSError:
            return False

    def _build_write_file_failure_message(self, outcome: WriteFileOutcome) -> str:
        """构造未确认落盘时的统一最终说明。"""
        lines = ["仅生成了候选实现，未成功落盘。"]
        if outcome.attempted_paths:
            lines.append("候选写入路径：")
            lines.extend([f"- {path}" for path in outcome.attempted_paths])
        else:
            lines.append("本次规划包含 write_file 步骤，但没有拿到可确认的写入结果。")
        lines.append("未确认 write_file 已执行成功并且目标文件存在，因此不能表述为“已完成写入”。")
        return "\n".join(lines)

    def _build_plan_failure_message(
        self,
        plan: list[PlanStep],
        step_results: list[RunResult],
    ) -> str:
        """当规划中的某一步失败时，返回确定性的失败说明，不再交给模型总结。"""
        failed_step: PlanStep | None = None
        failed_result: RunResult | None = None
        for step, result in zip(plan, step_results):
            if step.status == "failed" or result.status == "failed":
                failed_step = step
                failed_result = result
                break

        if failed_step is None:
            return "规划执行失败，未生成可靠结果。"

        lines = [f"规划执行未完成，失败步骤：{failed_step.title}。"]
        if failed_result is not None and failed_result.final_output:
            lines.append("失败原因：")
            lines.append(failed_result.final_output)
        lines.append("由于规划步骤未成功完成，本次结果不能表述为“已完成实现”或“已完成写入”。")
        return "\n".join(lines)

    def _build_failed_plan_result(
        self,
        *,
        model: str,
        reasoning_mode: str,
        session_id: str,
        total_step_count: int,
        plan: list[PlanStep],
        usage: RunUsage | None,
        metrics: RunMetrics | None,
        direct_tool_execution_used: bool,
        message: str,
        run_id: str | None,
    ) -> RunResult:
        """构造统一的规划失败结果。"""
        return RunResult(
            id=f"planner-summary-skipped-{uuid4()}",
            model=model,
            reasoning_mode=reasoning_mode,
            choices=[
                RunChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=message),
                    finish_reason="stop",
                )
            ],
            run_id=run_id,
            session_id=session_id,
            step_count=total_step_count,
            status="failed",
            final_output=message,
            plan=plan,
            usage=usage,
            metrics=metrics,
            direct_tool_execution_used=direct_tool_execution_used,
        )
