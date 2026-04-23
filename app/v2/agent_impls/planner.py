"""Planner agent implementation."""

from __future__ import annotations

import json

from app.contracts.agent import AgentArtifact, AgentResult, AgentSpec, AgentTask, SharedWorkspace
from app.contracts.planner import Plan, PlanStep
from app.v1.planner.simple_planner import SimplePlanner
from app.v2.agent_impls.llm_utils import chat_json
from app.v2.agent_impls.payloads import PLANNER_TOOL_HINTS, PlannerOutputPayload
from app.v2.base import AgentBase, AgentContext


class PlannerAgent(AgentBase):
    """将用户目标转成结构化计划。

    输入契约：
    - task.goal：用户目标与当前规划请求。
    - prompt_context：current_plan / project_summary / latest_test_result。
    - workspace：提供 replan_count 等共享状态。

    输出契约：
    - AgentResult.status：completed。
    - output_data.plan：结构化 Plan（包含 step、suggested_agent、success_criteria）。
    - artifacts：plan 工件摘要。
    """

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
        payload = chat_json(context=context, system_prompt=system_prompt, user_prompt=user_prompt)
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
