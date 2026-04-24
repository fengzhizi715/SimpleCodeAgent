"""V2 Orchestrator Runtime。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.contracts.message import ChatMessage
from app.contracts.agent import AgentResult, AgentTask, DelegationRecord, SharedWorkspace, TestReport
from app.contracts.planner import Plan
from app.contracts.run import RunChoice, RunMetrics, RunResult, RunUsage
from app.contracts.trace import TraceEvent
from app.core.logger import get_logger
from app.llm.client import LLMProvider
from app.trace.recorder import JsonlTraceRecorder
from app.trace.repository import SQLiteTraceRepository
from app.v1.tools.registry import ToolRegistry
from app.v2.base import AgentContext, OrchestratorDelegationClient
from app.v2.context import ContextBuilder
from app.v2.replay import (
    build_delegation_tree,
    build_execution_log,
    build_execution_nodes,
    build_teaching_view,
)
from app.v2.registry import AgentRegistry
from app.v2.repository import V2Repository
from app.v2.workspace import WorkspaceStore

logger = get_logger(__name__)


class OrchestratorRuntime:
    """中心化多 Agent 主执行循环。"""

    def __init__(
        self,
        *,
        registry: AgentRegistry,
        trace_repository: SQLiteTraceRepository,
        v2_repository: V2Repository | None = None,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self.registry = registry
        self.trace_repository = trace_repository
        self.v2_repository = v2_repository or V2Repository(trace_repository.db)
        self.context_builder = context_builder or ContextBuilder()

    def _timestamp(self) -> str:
        return datetime.now(UTC).isoformat()

    def _make_trace_event(
        self,
        *,
        run_id: str,
        session_id: str,
        event_type: str,
        message: str,
        actor: str | None = None,
        action: str | None = None,
        status: str | None = None,
        input_summary: str | None = None,
        output_summary: str | None = None,
        payload: dict[str, object] | None = None,
        parent_event_id: str | None = None,
    ) -> TraceEvent:
        timestamp = self._timestamp()
        return TraceEvent(
            run_id=run_id,
            root_run_id=run_id,
            session_id=session_id,
            actor=actor,
            action=action,
            status=status,
            input_summary=input_summary,
            output_summary=output_summary,
            started_at=timestamp,
            ended_at=timestamp,
            parent_event_id=parent_event_id,
            event_type=event_type,
            message=message,
            payload=payload or {},
        )

    def run(
        self,
        *,
        provider: LLMProvider,
        model: str,
        task: str,
        session_id: str,
        tool_registry: ToolRegistry,
        workspace_root: str | Path,
        reasoning_mode: str = "default",
        max_steps: int = 8,
        run_timeout_seconds: int = 120,
        max_replans: int = 1,
        enabled_agents: set[str] | list[str] | tuple[str, ...] | None = None,
    ) -> RunResult:
        run_id = str(uuid4())
        trace_recorder = JsonlTraceRecorder(run_id=run_id)
        workspace = SharedWorkspace(session_id=session_id, run_id=run_id, user_goal=task)
        workspace_store = WorkspaceStore(workspace, workspace_root=workspace_root)
        allowed_agents = self._normalize_enabled_agents(enabled_agents)
        workspace.private_context["orchestrator"] = {"enabled_agents": sorted(allowed_agents)}
        context = AgentContext(
            provider=provider,
            model=model,
            reasoning_mode=reasoning_mode,
            tool_registry=tool_registry,
            trace_repository=self.trace_repository,
            trace_recorder=trace_recorder,
            workspace_root=Path(workspace_root).resolve(),
            session_id=session_id,
            run_id=run_id,
        )
        delegation_client = OrchestratorDelegationClient(self._call_agent)
        trace_events: list[TraceEvent] = []
        delegation_records: list[DelegationRecord] = []
        delegation_start_event_ids: dict[str, str] = {}
        aggregate_usage = RunUsage()
        aggregate_metrics = RunMetrics()
        started_at = datetime.now(UTC)
        self.v2_repository.ensure_session(session_id)
        self.v2_repository.ensure_run(
            run_id=run_id,
            session_id=session_id,
            model=model,
            task=task,
            workdir=str(Path(workspace_root).resolve()),
            status="running",
        )
        self.v2_repository.save_workspace(workspace)

        run_started_event = self._make_trace_event(
            run_id=run_id,
            session_id=session_id,
            actor="orchestrator",
            action="run",
            status="started",
            input_summary=task,
            event_type="run_started",
            message="V2 orchestrator run started.",
        )
        self._record_trace(trace_events, trace_recorder, run_started_event)

        planner_result = delegation_client.delegate(
            agent_id="planner",
            task=AgentTask(
                session_id=session_id,
                run_id=run_id,
                goal=task,
                step_type="planning",
                target_agent="planner",
            ),
            workspace=workspace,
            context=context,
            trace_events=trace_events,
            delegation_records=delegation_records,
            delegation_start_event_ids=delegation_start_event_ids,
            parent_event_id=run_started_event.id,
        )
        self._accumulate_agent_result(
            aggregate_usage=aggregate_usage,
            aggregate_metrics=aggregate_metrics,
            result=planner_result,
        )
        if planner_result.status != "completed":
            return self._build_failure_result(
                run_id=run_id,
                session_id=session_id,
                model=model,
                reasoning_mode=reasoning_mode,
                task=task,
                workdir=str(Path(workspace_root).resolve()),
                message=planner_result.error_message or planner_result.summary,
                trace_events=trace_events,
                aggregate_usage=aggregate_usage,
                aggregate_metrics=aggregate_metrics,
                started_at=started_at,
                step_count=0,
                trace_recorder=trace_recorder,
            )

        plan = Plan.model_validate(planner_result.output_data.get("plan", {}))
        plan = self._filter_plan_by_enabled_agents(plan=plan, enabled_agents=allowed_agents)
        workspace_store.set_plan(plan)
        workspace_store.add_artifact(key="plan", artifact_type="plan", summary=plan.summary)
        self.v2_repository.save_workspace(workspace)
        self._record_trace(
            trace_events,
            trace_recorder,
            self._make_trace_event(
                run_id=run_id,
                session_id=session_id,
                actor="orchestrator",
                action="planning",
                status="completed",
                output_summary=plan.summary,
                event_type="workspace_updated",
                message="Initial plan stored in shared workspace.",
                payload={"step_count": len(plan.steps)},
                parent_event_id=run_started_event.id,
            ),
        )

        executed_steps = 0
        replan_count = 0
        step_index = 0
        while workspace.current_plan and step_index < len(workspace.current_plan.steps):
            elapsed_seconds = (datetime.now(UTC) - started_at).total_seconds()
            if elapsed_seconds >= run_timeout_seconds:
                return self._build_failure_result(
                    run_id=run_id,
                    session_id=session_id,
                    model=model,
                    reasoning_mode=reasoning_mode,
                    task=task,
                    workdir=str(Path(workspace_root).resolve()),
                    message=f"已达到运行超时时间（{run_timeout_seconds}s），系统已主动停止。",
                    trace_events=trace_events,
                    aggregate_usage=aggregate_usage,
                    aggregate_metrics=aggregate_metrics,
                    started_at=started_at,
                    step_count=executed_steps,
                    trace_recorder=trace_recorder,
                )
            if executed_steps >= max_steps:
                return self._build_failure_result(
                    run_id=run_id,
                    session_id=session_id,
                    model=model,
                    reasoning_mode=reasoning_mode,
                    task=task,
                    workdir=str(Path(workspace_root).resolve()),
                    message="已达到 V2 最大执行步数，系统主动停止以避免无限循环。",
                    trace_events=trace_events,
                    aggregate_usage=aggregate_usage,
                    aggregate_metrics=aggregate_metrics,
                    started_at=started_at,
                    step_count=executed_steps,
                    trace_recorder=trace_recorder,
                )
            step = workspace.current_plan.steps[step_index]
            executed_steps += 1
            step.status = "in_progress"
            step_task = AgentTask(
                session_id=session_id,
                run_id=run_id,
                step_id=step.id,
                goal=step.goal or step.description or step.title,
                step_type=step.type,
                target_agent=step.suggested_agent or "coder",
                input_data=self._build_step_input(step),
                success_criteria=list(step.success_criteria),
                retry_count=step.retry_count,
                max_retries=step.max_retries,
            )
            result = delegation_client.delegate(
                agent_id=step_task.target_agent,
                task=step_task,
                workspace=workspace,
                context=context,
                trace_events=trace_events,
                delegation_records=delegation_records,
                delegation_start_event_ids=delegation_start_event_ids,
                parent_event_id=run_started_event.id,
            )
            self._accumulate_agent_result(
                aggregate_usage=aggregate_usage,
                aggregate_metrics=aggregate_metrics,
                result=result,
            )
            self._apply_agent_result(
                result=result,
                step_task=step_task,
                workspace_store=workspace_store,
            )
            self.v2_repository.save_workspace(workspace)
            if result.artifacts:
                self.v2_repository.save_artifacts(
                    run_id=run_id,
                    session_id=session_id,
                    artifacts=self._prepare_artifacts(
                        artifacts=result.artifacts,
                        workspace=workspace,
                        producer_agent=step_task.target_agent,
                    ),
                )
            if result.status == "completed":
                if (
                    step_task.target_agent == "coder"
                    and "reviewer" in allowed_agents
                    and self.registry.get("reviewer") is not None
                ):
                    self._run_review_step(
                    workspace=workspace,
                    context=context,
                    delegation_client=delegation_client,
                    trace_events=trace_events,
                    delegation_records=delegation_records,
                    workspace_store=workspace_store,
                        step=step,
                    )
                step.status = "completed"
                step.output_summary = result.summary
                step_index += 1
                continue
            step.status = "failed"
            step.output_summary = result.error_message or result.summary
            if step_task.target_agent == "tester" and workspace.latest_test_result is not None:
                recovered = self._handle_test_failure_feedback(
                    workspace=workspace,
                    context=context,
                    delegation_client=delegation_client,
                    trace_events=trace_events,
                    delegation_records=delegation_records,
                    failed_step=step,
                )
                if recovered:
                    step.retry_count += 1
                    step.status = "pending"
                    continue

            if replan_count < max_replans:
                replan_count += 1
                replanned = self._replan(
                    workspace=workspace,
                    context=context,
                    delegation_client=delegation_client,
                    trace_events=trace_events,
                    delegation_records=delegation_records,
                    failed_step=step,
                )
                if replanned:
                    step_index = 0
                    continue
            return self._build_failure_result(
                run_id=run_id,
                session_id=session_id,
                model=model,
                reasoning_mode=reasoning_mode,
                task=task,
                workdir=str(Path(workspace_root).resolve()),
                message=result.error_message or result.summary,
                trace_events=trace_events,
                aggregate_usage=aggregate_usage,
                aggregate_metrics=aggregate_metrics,
                started_at=started_at,
                step_count=executed_steps,
                trace_recorder=trace_recorder,
            )

        final_output = self._compose_final_answer(workspace=workspace, delegation_records=delegation_records)
        incomplete_reason = self._assess_incomplete_reason(
            workspace=workspace,
            delegation_records=delegation_records,
        )
        if incomplete_reason:
            return self._build_failure_result(
                run_id=run_id,
                session_id=session_id,
                model=model,
                reasoning_mode=reasoning_mode,
                task=task,
                workdir=str(Path(workspace_root).resolve()),
                message=f"{final_output}\n\n未完成原因：{incomplete_reason}",
                trace_events=trace_events,
                aggregate_usage=aggregate_usage,
                aggregate_metrics=aggregate_metrics,
                started_at=started_at,
                step_count=executed_steps,
                trace_recorder=trace_recorder,
            )
        finished_event = self._make_trace_event(
            run_id=run_id,
            session_id=session_id,
            actor="orchestrator",
            action="run",
            status="completed",
            output_summary=final_output,
            event_type="run_finished",
            message="V2 orchestrator run finished.",
            payload={"executed_steps": executed_steps, "replan_count": replan_count},
            parent_event_id=run_started_event.id,
        )
        self._record_trace(trace_events, trace_recorder, finished_event)
        self.trace_repository.save_events(run_id, trace_events)
        duration_seconds = max((datetime.now(UTC) - started_at).total_seconds(), 0.0)
        final_result = RunResult(
            id=run_id,
            model=model,
            reasoning_mode=reasoning_mode,
            choices=[RunChoice(index=0, message=ChatMessage(role="assistant", content=final_output))],
            usage=aggregate_usage,
            metrics=aggregate_metrics.model_copy(update={"duration_seconds": duration_seconds}),
            run_id=run_id,
            session_id=session_id,
            step_count=executed_steps,
            status="completed",
            final_output=final_output,
            plan=list(workspace.current_plan.steps) if workspace.current_plan else [],
            trace=trace_events,
        )
        self.v2_repository.save_run(final_result, task, workdir=str(Path(workspace_root).resolve()))
        self.v2_repository.save_workspace(workspace)
        return final_result

    def get_run_replay(self, run_id: str) -> dict[str, object]:
        """返回某次 V2 run 的回放数据。"""
        replay = self.v2_repository.list_run_replay(run_id)
        replay["trace"] = [
            event.model_dump()
            for event in self.trace_repository.query_timeline(run_id)
        ]
        replay["execution_log"] = build_execution_log(
            trace=replay["trace"],
            delegations=replay.get("delegations", []),  # type: ignore[arg-type]
        )
        replay["delegation_tree"] = build_delegation_tree(
            replay.get("delegations", [])  # type: ignore[arg-type]
        )
        replay["execution_nodes"] = build_execution_nodes(
            run=replay.get("run"),  # type: ignore[arg-type]
            workspace=replay.get("workspace"),  # type: ignore[arg-type]
            execution_log=replay["execution_log"],  # type: ignore[arg-type]
            delegation_tree=replay["delegation_tree"],  # type: ignore[arg-type]
            artifacts=replay.get("artifacts", []),  # type: ignore[arg-type]
        )
        replay["teaching_view"] = build_teaching_view(
            run=replay.get("run"),  # type: ignore[arg-type]
            workspace=replay.get("workspace"),  # type: ignore[arg-type]
            execution_log=replay["execution_log"],  # type: ignore[arg-type]
            delegation_tree=replay["delegation_tree"],  # type: ignore[arg-type]
        )
        return replay

    def get_session_replay(self, session_id: str) -> dict[str, object]:
        """返回某个 session 的聚合回放数据。"""
        replay = self.v2_repository.list_session_replay(session_id)
        replay["trace"] = [
            event.model_dump()
            for event in self.trace_repository.query_timeline_by_session(session_id)
        ]
        replay["execution_log"] = build_execution_log(
            trace=replay["trace"],
            delegations=replay.get("delegations", []),  # type: ignore[arg-type]
        )
        replay["delegation_tree"] = build_delegation_tree(
            replay.get("delegations", [])  # type: ignore[arg-type]
        )
        latest_run = replay["runs"][-1] if replay.get("runs") else None  # type: ignore[index]
        latest_workspace = replay["workspaces"][-1] if replay.get("workspaces") else None  # type: ignore[index]
        replay["execution_nodes"] = build_execution_nodes(
            run=latest_run,
            workspace=latest_workspace,
            execution_log=replay["execution_log"],  # type: ignore[arg-type]
            delegation_tree=replay["delegation_tree"],  # type: ignore[arg-type]
            artifacts=replay.get("artifacts", []),  # type: ignore[arg-type]
        )
        replay["teaching_view"] = build_teaching_view(
            run=latest_run,
            workspace=latest_workspace,
            execution_log=replay["execution_log"],  # type: ignore[arg-type]
            delegation_tree=replay["delegation_tree"],  # type: ignore[arg-type]
        )
        return replay

    def list_recent_runs_for_ui(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, object]]:
        """返回最近若干次带 workspace 的 V2 运行摘要。"""
        return self.v2_repository.list_recent_runs_with_workspace(limit=limit, offset=offset)

    def count_runs_for_ui(self) -> int:
        """返回带 workspace 的 V2 运行总数。"""
        return self.v2_repository.count_runs_with_workspace()

    def delete_run_for_ui(self, run_id: str) -> bool:
        """删除单条 V2 run 及其关联记录。"""
        return self.v2_repository.delete_run_for_ui(run_id)

    def _call_agent(
        self,
        *,
        agent_id: str,
        task: AgentTask,
        workspace: SharedWorkspace,
        context: AgentContext,
        trace_events: list[TraceEvent],
        delegation_records: list[DelegationRecord],
        delegation_start_event_ids: dict[str, str],
        parent_event_id: str | None = None,
    ) -> AgentResult:
        agent = self.registry.get(agent_id)
        if agent is None:
            return AgentResult(
                task_id=task.task_id,
                agent_id=agent_id,
                status="failed",
                summary=f"Agent not found: {agent_id}",
                error_message=f"Agent not found: {agent_id}",
            )
        prompt_context = self.context_builder.build(agent=agent.spec, task=task, workspace=workspace)
        selected_event = self._make_trace_event(
            run_id=context.run_id,
            session_id=context.session_id,
            actor="orchestrator",
            action="agent-select",
            status="completed",
            input_summary=task.goal,
            output_summary=agent_id,
            event_type="agent_selected",
            message=f"Selected agent {agent_id} for delegated step.",
            payload={"task_id": task.task_id, "step_id": task.step_id},
            parent_event_id=parent_event_id,
        )
        self._record_trace(trace_events, context.trace_recorder, selected_event)
        delegation = DelegationRecord(
            run_id=context.run_id,
            session_id=context.session_id,
            step_id=task.step_id,
            parent_agent_id="orchestrator",
            target_agent=agent_id,
            task_id=task.task_id,
            status="running",
            summary=task.goal,
        )
        delegation_records.append(delegation)
        self.v2_repository.save_delegation(delegation)
        delegation_started_event = self._make_trace_event(
            run_id=context.run_id,
            session_id=context.session_id,
            actor="orchestrator",
            action="delegation",
            status="started",
            input_summary=task.goal,
            event_type="delegation_started",
            message=f"Delegating step to {agent_id}.",
            payload={"task_id": task.task_id, "step_id": task.step_id, "target_agent": agent_id},
            parent_event_id=selected_event.id,
        )
        delegation_start_event_ids[task.task_id] = delegation_started_event.id
        self._record_trace(trace_events, context.trace_recorder, delegation_started_event)
        result = agent.run(task=task, workspace=workspace, context=context, prompt_context=prompt_context)
        delegation.status = "completed" if result.status == "completed" else "failed"
        delegation.error_message = result.error_message
        delegation.summary = result.summary
        delegation.finished_at = datetime.now(UTC).isoformat()
        self.v2_repository.save_delegation(delegation)
        self._record_trace(
            trace_events,
            context.trace_recorder,
            self._make_trace_event(
                run_id=context.run_id,
                session_id=context.session_id,
                actor=agent_id,
                action=task.step_type,
                status=result.status,
                input_summary=task.goal,
                output_summary=result.summary,
                event_type="delegation_finished",
                message=f"{agent_id} finished delegated task.",
                payload={"task_id": task.task_id, "step_id": task.step_id, "result_status": result.status},
                parent_event_id=delegation_start_event_ids.get(task.task_id),
            ),
        )
        return result

    def _apply_agent_result(
        self,
        *,
        result: AgentResult,
        step_task: AgentTask,
        workspace_store: WorkspaceStore,
    ) -> None:
        workspace_store.append_note(f"{step_task.target_agent}: {result.summary}")
        workspace_store.upsert_agent_artifacts(result.artifacts)
        if step_task.target_agent == "analyst":
            merged_analysis = workspace_store.merge_analyst_context(result.output_data)
            summary = str(merged_analysis.get("project_summary") or result.summary)
            workspace_store.add_artifact(
                key="project_summary",
                artifact_type="analysis",
                summary="项目分析摘要",
                metadata={
                    "entry_files": merged_analysis.get("entry_files", []),
                    "key_files": merged_analysis.get("key_files", []),
                },
            )
            return
        if step_task.target_agent == "coder":
            workspace_store.write_patch_summary(result.summary)
            workspace_store.add_artifact(
                key="patch_summary",
                artifact_type="patch",
                summary=result.summary[:120],
                metadata={
                    "modified_files": result.output_data.get("modified_files", []),
                    "created_files": result.output_data.get("created_files", []),
                    "deleted_files": result.output_data.get("deleted_files", []),
                },
            )
            workspace_store.upsert_private_context("coder", result.output_data)
            return
        if step_task.target_agent == "reviewer":
            workspace_store.add_artifact(
                key="review_report",
                artifact_type="review",
                summary=result.summary[:120],
                metadata={"issue_count": len(result.output_data.get("issues", []))},
            )
            workspace_store.upsert_private_context("reviewer", result.output_data)
            return
        if step_task.target_agent == "tester":
            report = TestReport.model_validate(result.output_data.get("test_report", {}))
            workspace_store.write_test_result(report)
            workspace_store.add_artifact(
                key="latest_test_result",
                artifact_type="test-report",
                summary=report.summary,
                metadata={"executed_command": report.executed_command},
            )
            workspace_store.upsert_private_context("tester", result.output_data)

    def _run_review_step(
        self,
        *,
        workspace: SharedWorkspace,
        context: AgentContext,
        delegation_client: OrchestratorDelegationClient,
        trace_events: list[TraceEvent],
        delegation_records: list[DelegationRecord],
        workspace_store: WorkspaceStore,
        step,
    ) -> None:
        review_task = AgentTask(
            session_id=context.session_id,
            run_id=context.run_id,
            step_id=step.id,
            goal="Review 最新代码改动，检查明显风险和可维护性问题。",
            step_type="review",
            target_agent="reviewer",
            input_data={},
            success_criteria=["输出 review 摘要和 issues 列表"],
        )
        review_result = delegation_client.delegate(
            agent_id="reviewer",
            task=review_task,
            workspace=workspace,
            context=context,
            trace_events=trace_events,
            delegation_records=delegation_records,
            delegation_start_event_ids={},
        )
        self._apply_agent_result(
            result=review_result,
            step_task=review_task,
            workspace_store=workspace_store,
        )
        if review_result.artifacts:
            self.v2_repository.save_artifacts(
                run_id=context.run_id,
                session_id=context.session_id,
                artifacts=self._prepare_artifacts(
                    artifacts=review_result.artifacts,
                    workspace=workspace,
                    producer_agent="reviewer",
                ),
            )
        self.v2_repository.save_workspace(workspace)

    def _handle_test_failure_feedback(
        self,
        *,
        workspace: SharedWorkspace,
        context: AgentContext,
        delegation_client: OrchestratorDelegationClient,
        trace_events: list[TraceEvent],
        delegation_records: list[DelegationRecord],
        failed_step,
    ) -> bool:
        test_result = workspace.latest_test_result
        if test_result is None:
            return False
        # 未收集到任何用例时，Coder 没有可修复的断言/栈，回流只会空转打满步数；交给 RePlan / 新计划处理。
        if test_result.failure_type == "no_tests_collected":
            return False
        for line in test_result.key_logs:
            low = line.lower()
            if "no tests ran" in low or "collected 0 items" in low or "0 tests collected" in low:
                return False
        feedback_task = AgentTask(
            session_id=context.session_id,
            run_id=context.run_id,
            step_id=failed_step.id,
            goal=(
                "根据测试失败结果继续修复当前实现。"
                f" 失败摘要：{test_result.summary}"
            ),
            step_type="coding",
            target_agent="coder",
            input_data={"test_report": test_result.model_dump()},
            success_criteria=["修复当前失败原因，并给出变更摘要"],
            retry_count=failed_step.retry_count,
            max_retries=1,
        )
        coder_result = delegation_client.delegate(
            agent_id="coder",
            task=feedback_task,
            workspace=workspace,
            context=context,
            trace_events=trace_events,
            delegation_records=delegation_records,
            delegation_start_event_ids={},
        )
        if coder_result.status != "completed":
            return False
        self._apply_agent_result(
            result=coder_result,
            step_task=feedback_task,
            workspace_store=WorkspaceStore(workspace, workspace_root=context.workspace_root),
        )
        return True

    def _replan(
        self,
        *,
        workspace: SharedWorkspace,
        context: AgentContext,
        delegation_client: OrchestratorDelegationClient,
        trace_events: list[TraceEvent],
        delegation_records: list[DelegationRecord],
        failed_step,
    ) -> bool:
        replan_started_event = self._make_trace_event(
            run_id=context.run_id,
            session_id=context.session_id,
            actor="orchestrator",
            action="replan",
            status="started",
            input_summary=failed_step.output_summary,
            event_type="replan_started",
            message="Replanning after failed step.",
            payload={"failed_step_id": failed_step.id},
        )
        self._record_trace(trace_events, context.trace_recorder, replan_started_event)
        planner_result = delegation_client.delegate(
            agent_id="planner",
            task=AgentTask(
                session_id=context.session_id,
                run_id=context.run_id,
                goal=(
                    f"{workspace.user_goal}\n"
                    f"已失败步骤：{failed_step.title}\n"
                    f"失败信息：{failed_step.output_summary or ''}"
                ),
                step_type="planning",
                target_agent="planner",
            ),
            workspace=workspace,
            context=context,
            trace_events=trace_events,
            delegation_records=delegation_records,
            delegation_start_event_ids={},
            parent_event_id=replan_started_event.id,
        )
        if planner_result.status != "completed":
            return False
        plan = Plan.model_validate(planner_result.output_data.get("plan", {}))
        plan = self._filter_plan_by_enabled_agents(plan=plan, enabled_agents=self._enabled_agents_from_workspace(workspace))
        plan.replan_count = (workspace.current_plan.replan_count if workspace.current_plan else 0) + 1
        workspace.current_plan = plan
        self.v2_repository.save_workspace(workspace)
        self._record_trace(
            trace_events,
            context.trace_recorder,
            self._make_trace_event(
                run_id=context.run_id,
                session_id=context.session_id,
                actor="orchestrator",
                action="replan",
                status="completed",
                output_summary=plan.summary,
                event_type="replan_finished",
                message="Replan completed.",
                payload={"step_count": len(plan.steps)},
                parent_event_id=replan_started_event.id,
            ),
        )
        return True

    def _build_step_input(self, step) -> dict[str, object]:
        input_data: dict[str, object] = {}
        step_type = getattr(step, "type", "")
        if step_type == "testing":
            vcmd = getattr(step, "verification_command", None)
            if isinstance(vcmd, str) and vcmd.strip():
                input_data["command"] = vcmd.strip()
        input_data["step_title"] = str(getattr(step, "title", "") or "")
        input_summary = getattr(step, "input_summary", None)
        if input_summary:
            input_data["input_summary"] = input_summary
        tool_name = getattr(step, "tool_name", None)
        if tool_name:
            input_data["tool_name"] = tool_name
        if step_type == "analysis":
            input_data["analysis_mode"] = self._infer_analysis_mode(step)
        return input_data

    def _normalize_enabled_agents(self, enabled_agents: set[str] | list[str] | tuple[str, ...] | None) -> set[str]:
        registered = {spec.agent_id for spec in self.registry.list_specs()}
        if enabled_agents is None:
            allowed = set(registered)
        else:
            allowed = {str(agent_id).strip() for agent_id in enabled_agents if str(agent_id).strip()}
            allowed &= registered
        allowed.add("planner")
        return allowed

    def _enabled_agents_from_workspace(self, workspace: SharedWorkspace) -> set[str]:
        orchestrator_context = workspace.private_context.get("orchestrator", {})
        if isinstance(orchestrator_context, dict):
            raw = orchestrator_context.get("enabled_agents")
            if isinstance(raw, list):
                return self._normalize_enabled_agents(raw)
        return self._normalize_enabled_agents(None)

    def _filter_plan_by_enabled_agents(self, *, plan: Plan, enabled_agents: set[str]) -> Plan:
        plan.metadata["enabled_agents"] = sorted(enabled_agents)
        kept_steps = [
            step
            for step in plan.steps
            if not step.suggested_agent or step.suggested_agent in enabled_agents
        ]
        skipped = [
            step.suggested_agent
            for step in plan.steps
            if step.suggested_agent and step.suggested_agent not in enabled_agents
        ]
        if skipped:
            plan.metadata["skipped_disabled_agents"] = skipped
        plan.steps = kept_steps
        return plan

    def _infer_analysis_mode(self, step) -> str:
        title = str(getattr(step, "title", "") or "").lower()
        goal = str(getattr(step, "goal", "") or "").lower()
        tool_name = str(getattr(step, "tool_name", "") or "").lower()
        haystack = " ".join(part for part in [title, goal, tool_name] if part)
        if any(token in haystack for token in ("总结", "汇总", "概述", "summary", "summar", "final")):
            return "summary"
        if any(token in haystack for token in ("read_file", "读取", "关键文件", "配置文件", "入口文件")):
            return "key_file_read"
        return "directory_scan"

    def _compose_final_answer(
        self,
        *,
        workspace: SharedWorkspace,
        delegation_records: list[DelegationRecord],
    ) -> str:
        lines = [f"目标：{workspace.user_goal}"]
        analyst_context = workspace.private_context.get("analyst", {})
        project_summary = str(analyst_context.get("project_summary") or workspace.project_summary).strip()
        if project_summary:
            lines.append(f"项目分析：{project_summary}")
        module_responsibilities = analyst_context.get("module_responsibilities", {})
        if isinstance(module_responsibilities, dict) and module_responsibilities:
            pairs = [
                f"{str(name)}: {str(summary)}"
                for name, summary in list(module_responsibilities.items())[:6]
                if str(name).strip() and str(summary).strip()
            ]
            if pairs:
                lines.append(f"模块职责：{'；'.join(pairs)}")
        if analyst_context.get("entry_files"):
            lines.append(f"关键入口：{', '.join(str(item) for item in analyst_context['entry_files'][:5])}")
        key_files = analyst_context.get("key_files", [])
        if isinstance(key_files, list) and key_files:
            key_file_labels: list[str] = []
            for item in key_files[:5]:
                if isinstance(item, dict) and item.get("path"):
                    label = str(item["path"])
                    reason = str(item.get("reason") or "").strip()
                    key_file_labels.append(f"{label}({reason})" if reason else label)
                elif isinstance(item, str):
                    key_file_labels.append(item)
            if key_file_labels:
                lines.append(f"关键文件：{', '.join(key_file_labels)}")
        coding_hints = analyst_context.get("coding_hints", [])
        if isinstance(coding_hints, list) and coding_hints:
            lines.append(f"开发提示：{'；'.join(str(item) for item in coding_hints[:3])}")
        if workspace.latest_patch_summary:
            lines.append(f"代码改动：{workspace.latest_patch_summary}")
        coder_context = workspace.private_context.get("coder", {})
        changed_files = [
            *[str(path) for path in coder_context.get("modified_files", [])],
            *[str(path) for path in coder_context.get("created_files", [])],
        ]
        if changed_files:
            lines.append(f"涉及文件：{', '.join(changed_files[:8])}")
        risk_notes = [str(note) for note in coder_context.get("risk_notes", []) if str(note).strip()]
        if risk_notes:
            lines.append(f"风险提示：{'；'.join(risk_notes[:3])}")
        reviewer_context = workspace.private_context.get("reviewer", {})
        review_issues = reviewer_context.get("issues", []) if isinstance(reviewer_context, dict) else []
        if isinstance(review_issues, list) and review_issues:
            lines.append(f"Review 发现问题数：{len(review_issues)}")
        if workspace.latest_test_result is not None:
            lines.append(
                f"测试结果：{workspace.latest_test_result.status}，"
                f"{workspace.latest_test_result.summary}"
            )
            lines.append(f"验证命令：{workspace.latest_test_result.executed_command}")
        if delegation_records:
            lines.append(f"共执行 {len(delegation_records)} 次委派。")
        return "\n".join(lines)

    def _assess_incomplete_reason(
        self,
        *,
        workspace: SharedWorkspace,
        delegation_records: list[DelegationRecord],
    ) -> str | None:
        if workspace.latest_test_result is not None and workspace.latest_test_result.status != "passed":
            return (
                "最后一次验证未通过，不能将本次运行标记为完成。"
                f" 验证命令：{workspace.latest_test_result.executed_command}。"
                f" 结果：{workspace.latest_test_result.summary}"
            )

        if not self._looks_like_code_change_goal(workspace.user_goal):
            return None

        coder_context = workspace.private_context.get("coder", {})
        changed_files: list[str] = []
        if isinstance(coder_context, dict):
            for key in ("modified_files", "created_files", "deleted_files"):
                values = coder_context.get(key, [])
                if isinstance(values, list):
                    changed_files.extend(str(value) for value in values if str(value).strip())
        has_completed_coder = any(
            record.target_agent == "coder" and record.status == "completed"
            for record in delegation_records
        )
        if not workspace.latest_patch_summary and not changed_files and not has_completed_coder:
            return "用户目标属于代码修改/修复类任务，但本次运行没有产生 Coder 改动或补丁摘要。"
        return None

    def _looks_like_code_change_goal(self, goal: str) -> bool:
        normalized = goal.lower()
        change_keywords = (
            "修复",
            "bug",
            "实现",
            "增加",
            "新增",
            "修改",
            "改动",
            "优化",
            "fix",
            "bugfix",
            "implement",
            "add ",
            "change",
            "update",
            "refactor",
        )
        return any(keyword in normalized for keyword in change_keywords)

    def _accumulate_agent_result(
        self,
        *,
        aggregate_usage: RunUsage,
        aggregate_metrics: RunMetrics,
        result: AgentResult,
    ) -> None:
        if result.usage is not None:
            aggregate_usage.prompt_tokens += result.usage.prompt_tokens
            aggregate_usage.completion_tokens += result.usage.completion_tokens
            aggregate_usage.total_tokens += result.usage.total_tokens
        if result.metrics is not None:
            aggregate_metrics.llm_call_count += result.metrics.llm_call_count
            aggregate_metrics.tool_call_count += result.metrics.tool_call_count
            aggregate_metrics.tool_error_count += result.metrics.tool_error_count
            aggregate_metrics.memory_write_count += result.metrics.memory_write_count
            aggregate_metrics.fallback_count += result.metrics.fallback_count

    def _build_failure_result(
        self,
        *,
        run_id: str,
        session_id: str,
        model: str,
        reasoning_mode: str,
        task: str,
        workdir: str | None,
        message: str,
        trace_events: list[TraceEvent],
        aggregate_usage: RunUsage,
        aggregate_metrics: RunMetrics,
        started_at: datetime,
        step_count: int,
        trace_recorder: JsonlTraceRecorder,
    ) -> RunResult:
        failure_event = self._make_trace_event(
            run_id=run_id,
            session_id=session_id,
            actor="orchestrator",
            action="run",
            status="failed",
            output_summary=message,
            event_type="run_failed",
            message="V2 orchestrator run failed.",
        )
        self._record_trace(trace_events, trace_recorder, failure_event)
        self.trace_repository.save_events(run_id, trace_events)
        duration_seconds = max((datetime.now(UTC) - started_at).total_seconds(), 0.0)
        failed_result = RunResult(
            id=run_id,
            model=model,
            reasoning_mode=reasoning_mode,
            choices=[RunChoice(index=0, message=ChatMessage(role="assistant", content=message))],
            usage=aggregate_usage,
            metrics=aggregate_metrics.model_copy(update={"duration_seconds": duration_seconds}),
            run_id=run_id,
            session_id=session_id,
            step_count=step_count,
            status="failed",
            final_output=message,
            trace=trace_events,
        )
        self.v2_repository.save_run(
            failed_result,
            task,
            workdir=workdir,
        )
        return failed_result

    def _prepare_artifacts(
        self,
        *,
        artifacts: list,
        workspace: SharedWorkspace,
        producer_agent: str,
    ) -> list:
        version_by_key = {
            item.key: item.version
            for item in workspace.artifacts_index
        }
        prepared = []
        for artifact in artifacts:
            current_version = version_by_key.get(artifact.key, 1)
            prepared.append(
                artifact.model_copy(
                    update={
                        "version": artifact.version if artifact.version > 1 else current_version,
                        "producer_agent": artifact.producer_agent or producer_agent,
                    }
                )
            )
        return prepared

    def _record_trace(
        self,
        trace_events: list[TraceEvent],
        trace_recorder: JsonlTraceRecorder,
        event: TraceEvent,
    ) -> None:
        trace_events.append(event)
        trace_recorder.record(event)
