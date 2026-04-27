"""Planner agent implementation."""

from __future__ import annotations

import json

from app.contracts.agent import AgentArtifact, AgentResult, AgentSpec, AgentTask, SharedWorkspace
from app.contracts.planner import Plan, PlanStep
from app.contracts.run import RunMetrics, RunResult, RunUsage
from app.v1.planner.simple_planner import SimplePlanner
from app.v2.agent_impls.llm_utils import chat_json
from app.v2.agent_impls.payloads import PLANNER_TOOL_HINTS, PlannerOutputPayload
from app.v2.base import AgentBase, AgentContext
from app.v1.rag.rag_id_policy import strict_normalize_v2_rag_tokens
from app.v2.plan_policy import apply_step_list_policy, goal_uses_rag_shortcut


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
        raw_plan, usage, metrics = self._generate_plan(
            task=task,
            workspace=workspace,
            context=context,
            prompt_context=prompt_context,
        )
        replan_context = self._extract_replan_context(task=task, prompt_context=prompt_context)
        rag_enabled = self._rag_enabled(task=task, prompt_context=prompt_context)
        rag_shortcut_applied = rag_enabled and (not replan_context) and goal_uses_rag_shortcut(task.goal)
        selected_rag_ids = self._resolve_rag_ids(task=task, prompt_context=prompt_context) if rag_enabled else []
        selected_rag_id = selected_rag_ids[0] if selected_rag_ids else ""
        if not rag_enabled:
            raw_plan = self._strip_rag_steps(raw_plan)
        if not replan_context:
            raw_plan = apply_step_list_policy(
                raw_plan,
                user_goal=task.goal,
                project_summary=workspace.project_summary or "",
                enable_rag=rag_enabled,
            )
        plan = Plan(
            summary=f"Plan for: {task.goal}",
            steps=[
                self._explain_step(
                    step=self._enrich_step(step),
                    index=index,
                    replan_context=replan_context,
                    prompt_context=prompt_context,
                )
                for index, step in enumerate(raw_plan, start=1)
            ],
            replan_count=(workspace.current_plan.replan_count if workspace.current_plan else 0),
        )
        plan.metadata["planner_strategy"] = self._build_plan_strategy_metadata(
            plan=plan,
            prompt_context=prompt_context,
            replan_context=replan_context,
            rag_shortcut_applied=rag_shortcut_applied,
            selected_rag_id=selected_rag_id,
            selected_rag_ids=selected_rag_ids,
        )
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.spec.agent_id,
            status="completed",
            summary=f"生成 {len(plan.steps)} 个步骤的执行计划。",
            usage=usage,
            metrics=metrics,
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
    ) -> tuple[list[PlanStep], RunUsage | None, RunMetrics]:
        llm_plan, llm_result = self._generate_plan_with_llm(
            task=task,
            workspace=workspace,
            context=context,
            prompt_context=prompt_context,
        )
        metrics = RunMetrics(llm_call_count=1 if llm_result is not None else 0)
        usage = llm_result.usage if llm_result is not None else None
        if llm_plan:
            return llm_plan, usage, metrics
        replan_plan = self._build_replan_fallback(task=task, prompt_context=prompt_context)
        if replan_plan:
            metrics.fallback_count += 1
            return replan_plan, usage, metrics
        if self.planner.should_plan(task.goal):
            metrics.fallback_count += 1
            return self.planner.create_plan(task.goal), usage, metrics
        metrics.fallback_count += 1
        return [PlanStep(title="执行任务", goal=task.goal, description=task.goal)], usage, metrics

    def _generate_plan_with_llm(
        self,
        *,
        task: AgentTask,
        workspace: SharedWorkspace,
        context: AgentContext,
        prompt_context: dict[str, object],
    ) -> tuple[list[PlanStep] | None, RunResult | None]:
        system_prompt = (
            "You are the Planner Agent for SimpleCodeAgent V2. "
            "Return only valid JSON with keys summary and steps. "
            "Each step must contain title, goal, type, description, suggested_agent, "
            "input_requirements, success_criteria, and max_retries. "
            "Optional per step: verification_command (string shell command for testing/validation steps only; "
            "e.g. pytest tests/, ./gradlew test, mvn test — use when the repo is not plain Python pytest at root). "
            "type must be one of analysis, coding, testing, planning, validation, general. "
            "suggested_agent must be one of analyst, coder, tester. "
            "System may prepend an analysis step if the first step is unsafe; prefer analyst before coder/tester. "
            "Do not include markdown or explanations outside JSON."
        )
        user_prompt = "\n".join(
            [
                f"用户目标：{task.goal}",
                f"当前计划：{json.dumps(prompt_context.get('current_plan'), ensure_ascii=False)}",
                f"项目摘要：{prompt_context.get('project_summary', '')}",
                f"最近测试结果：{json.dumps(prompt_context.get('latest_test_result'), ensure_ascii=False)}",
                f"RAG 检索是否启用：{self._rag_enabled(task=task, prompt_context=prompt_context)}",
                f"重规划上下文：{json.dumps(self._extract_replan_context(task=task, prompt_context=prompt_context), ensure_ascii=False)}",
                f"Orchestrator 策略：{json.dumps(prompt_context.get('orchestrator_context'), ensure_ascii=False)}",
                "请输出 2-5 个可执行步骤；典型顺序是：分析/理解 → 实现 → 验证（可省略与目标无关的步）。",
                "如果 RAG 检索未启用，不要规划 retrieve_docs / RAG / 知识库检索步骤。",
                "如果这是 replan：优先解释如何绕开失败点；若 Tester 失败，通常回到 Coder 修复再 Tester 验证；若某 Agent 被禁用，不要规划给它。",
            ]
        )
        payload, llm_result = chat_json(context=context, system_prompt=system_prompt, user_prompt=user_prompt)
        if payload is None:
            return None, llm_result
        try:
            parsed = PlannerOutputPayload.model_validate(payload)
        except Exception:
            return None, llm_result
        if not parsed.steps:
            return None, llm_result
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
                verification_command=item.verification_command,
            )
            for item in parsed.steps
        ], llm_result

    def _enrich_step(self, step: PlanStep) -> PlanStep:
        step_type = step.type if step.type != "general" else self._infer_step_type(step)
        if step.tool_name in {"retrieve_docs", "list_dir", "read_file", "file_search"}:
            step_type = "analysis"
        if step.tool_name in {"shell_run"}:
            step_type = "testing"
        if step.tool_name in {"write_file", "replace_in_file", "multi_file_patch"}:
            step_type = "coding"
        routing_step = step.model_copy(update={"type": step_type})
        suggested_agent = self._resolve_suggested_agent(step=routing_step)
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

    def _explain_step(
        self,
        *,
        step: PlanStep,
        index: int,
        replan_context: dict[str, object],
        prompt_context: dict[str, object],
    ) -> PlanStep:
        explanation_parts = [
            f"第 {index} 步由 {step.suggested_agent or 'coder'} 执行，因为步骤类型是 {step.type}。",
        ]
        if step.strategy_explanation:
            explanation_parts.append(step.strategy_explanation)
        elif step.type == "analysis":
            explanation_parts.append("先补齐项目上下文，降低后续编码/验证的不确定性。")
        elif step.type == "coding":
            explanation_parts.append("该步骤负责产生局部代码改动，并承接已有分析或测试反馈。")
        elif step.type == "testing":
            explanation_parts.append("该步骤负责验证改动是否收敛，并把失败日志结构化反馈给 Orchestrator。")
        if replan_context:
            failed_agent = str(replan_context.get("failed_agent") or "").strip()
            failure_summary = str(replan_context.get("failure_summary") or "").strip()
            if failed_agent:
                explanation_parts.append(f"这是重规划后的步骤，需规避 {failed_agent} 上一步失败。")
            if failure_summary:
                explanation_parts.append(f"失败摘要：{failure_summary[:120]}")
        enabled_agents = self._enabled_agents_from_prompt(prompt_context)
        disabled_adjustment = ""
        if enabled_agents and step.suggested_agent and step.suggested_agent not in enabled_agents:
            disabled_adjustment = f"{step.suggested_agent} 当前被禁用，Orchestrator 会过滤或改写该步骤。"
        return step.model_copy(
            update={
                "strategy_explanation": " ".join(part for part in explanation_parts if part).strip(),
                "disabled_agent_adjustment": disabled_adjustment or step.disabled_agent_adjustment,
                "replan_reason": str(replan_context.get("failure_summary") or "") if replan_context else step.replan_reason,
            }
        )

    def _build_plan_strategy_metadata(
        self,
        *,
        plan: Plan,
        prompt_context: dict[str, object],
        replan_context: dict[str, object],
        rag_shortcut_applied: bool,
        selected_rag_id: str,
        selected_rag_ids: list[str],
    ) -> dict[str, object]:
        enabled_agents = sorted(self._enabled_agents_from_prompt(prompt_context))
        return {
            "mode": "replan" if replan_context else "initial_plan",
            "rag_shortcut_applied": rag_shortcut_applied,
            "selected_rag_id": selected_rag_id,
            "selected_rag_ids": selected_rag_ids,
            "enabled_agents": enabled_agents,
            "replan_context": replan_context,
            "step_explanations": [
                {
                    "step_id": step.id,
                    "target_agent": step.suggested_agent,
                    "explanation": step.strategy_explanation,
                    "disabled_agent_adjustment": step.disabled_agent_adjustment,
                }
                for step in plan.steps
            ],
        }

    def _resolve_rag_id(self, *, task: AgentTask, prompt_context: dict[str, object]) -> str:
        return self._resolve_rag_ids(task=task, prompt_context=prompt_context)[0]

    def _resolve_rag_ids(self, *, task: AgentTask, prompt_context: dict[str, object]) -> list[str]:
        values: list[str] = []
        raw_task_ids = task.input_data.get("rag_ids")
        if isinstance(raw_task_ids, list):
            values.extend(str(item).strip() for item in raw_task_ids)
        from_task = str(task.input_data.get("rag_id") or "").strip()
        if from_task:
            values.append(from_task)
        task_input = prompt_context.get("task_input")
        if isinstance(task_input, dict):
            raw_ctx_ids = task_input.get("rag_ids")
            if isinstance(raw_ctx_ids, list):
                values.extend(str(item).strip() for item in raw_ctx_ids)
            from_context = str(task_input.get("rag_id") or "").strip()
            if from_context:
                values.append(from_context)
        return strict_normalize_v2_rag_tokens(values)

    def _rag_enabled(self, *, task: AgentTask, prompt_context: dict[str, object]) -> bool:
        if task.input_data.get("rag_enabled") is False:
            return False
        task_input = prompt_context.get("task_input")
        if isinstance(task_input, dict) and task_input.get("rag_enabled") is False:
            return False
        return True

    def _strip_rag_steps(self, steps: list[PlanStep]) -> list[PlanStep]:
        stripped: list[PlanStep] = []
        for step in steps:
            haystack = " ".join(
                str(value or "")
                for value in (step.tool_name, step.title, step.goal, step.description)
            ).lower()
            if step.tool_name == "retrieve_docs" or "retrieve_docs" in haystack or "rag" in haystack:
                stripped.append(
                    step.model_copy(
                        update={
                            "tool_name": None,
                            "type": "analysis",
                            "strategy_explanation": "本次运行未启用 RAG，Planner 将检索步骤降级为普通上下文分析。",
                        }
                    )
                )
            else:
                stripped.append(step)
        return stripped

    def _extract_replan_context(self, *, task: AgentTask, prompt_context: dict[str, object]) -> dict[str, object]:
        raw = {}
        if isinstance(prompt_context.get("task_input"), dict):
            task_input = prompt_context["task_input"]
            raw_context = task_input.get("replan_context") if isinstance(task_input, dict) else None
            if isinstance(raw_context, dict):
                raw.update(raw_context)
        raw_context = task.input_data.get("replan_context") if isinstance(task.input_data, dict) else None
        if isinstance(raw_context, dict):
            raw.update(raw_context)
        return raw

    def _enabled_agents_from_prompt(self, prompt_context: dict[str, object]) -> set[str]:
        orchestrator_context = prompt_context.get("orchestrator_context")
        if not isinstance(orchestrator_context, dict):
            return set()
        policy = orchestrator_context.get("policy")
        raw = policy.get("enabled_agents") if isinstance(policy, dict) else orchestrator_context.get("enabled_agents")
        if not isinstance(raw, list):
            return set()
        return {str(item) for item in raw if str(item).strip()}

    def _build_replan_fallback(self, *, task: AgentTask, prompt_context: dict[str, object]) -> list[PlanStep]:
        replan_context = self._extract_replan_context(task=task, prompt_context=prompt_context)
        if not replan_context:
            return []
        enabled_agents = self._enabled_agents_from_prompt(prompt_context)
        failed_agent = str(replan_context.get("failed_agent") or "").strip()
        failure_summary = str(replan_context.get("failure_summary") or "上一步失败，需要调整执行路径。").strip()
        steps: list[PlanStep] = []
        if failed_agent == "tester":
            if not enabled_agents or "coder" in enabled_agents:
                steps.append(
                    PlanStep(
                        title="根据测试失败继续修复",
                        goal=f"根据最近测试失败结果修复实现。失败摘要：{failure_summary}",
                        type="coding",
                        description="重规划 fallback：Tester 失败后先回流给 Coder，而不是重复跑同一条验证命令。",
                        suggested_agent="coder",
                        input_requirements=["latest_test_result", "latest_patch_summary", "project_summary"],
                        success_criteria=["修改与失败日志直接相关的代码", "输出变更摘要和风险说明"],
                        strategy_explanation="Tester 失败通常说明实现仍未收敛，先让 Coder 根据日志修复。",
                        replan_reason=failure_summary,
                    )
                )
            if not enabled_agents or "tester" in enabled_agents:
                steps.append(
                    PlanStep(
                        title="重新验证修复结果",
                        goal="针对最新 Coder 改动重新运行合适的测试或构建命令。",
                        type="testing",
                        description="重规划 fallback：Coder 修复后再进入验证，避免直接宣称完成。",
                        suggested_agent="tester",
                        input_requirements=["latest_patch_summary", "modified_files", "latest_test_result"],
                        success_criteria=["输出新的结构化测试报告", "明确是否通过"],
                        strategy_explanation="修复后需要重新验证，形成失败回流后的闭环。",
                        replan_reason=failure_summary,
                    )
                )
        elif failed_agent == "coder":
            if not enabled_agents or "analyst" in enabled_agents:
                steps.append(
                    PlanStep(
                        title="补充失败相关上下文分析",
                        goal=f"分析 Coder 失败原因并定位更明确的关键文件。失败摘要：{failure_summary}",
                        type="analysis",
                        description="重规划 fallback：Coder 失败时先补上下文，降低下一次修改风险。",
                        suggested_agent="analyst",
                        input_requirements=["失败步骤", "project_summary", "execution_notes"],
                        success_criteria=["输出失败相关关键文件和编码提示"],
                        strategy_explanation="Coder 失败多半缺少上下文或目标文件线索，先回到 Analyst 补齐信息。",
                        replan_reason=failure_summary,
                    )
                )
            if not enabled_agents or "coder" in enabled_agents:
                steps.append(
                    PlanStep(
                        title="基于补充上下文重新修改",
                        goal="根据新的分析结果重新执行局部代码修改。",
                        type="coding",
                        description="重规划 fallback：使用更明确上下文重新编码。",
                        suggested_agent="coder",
                        input_requirements=["analysis_context", "失败摘要", "用户目标"],
                        success_criteria=["产生局部代码改动", "避免重复失败原因"],
                        strategy_explanation="补齐上下文后再让 Coder 修改，提升重试收敛概率。",
                        replan_reason=failure_summary,
                    )
                )
        if steps:
            return steps
        return [
            PlanStep(
                title="调整路径后继续执行",
                goal=f"根据失败信息调整下一步。失败摘要：{failure_summary}",
                type="general",
                description="重规划 fallback：没有匹配专用规则时，保留一个可解释的下一步。",
                suggested_agent=self._first_enabled_specialist(enabled_agents),
                input_requirements=["失败摘要", "当前 workspace"],
                success_criteria=["输出可继续执行的结构化结果"],
                strategy_explanation="未匹配专用重规划规则，选择当前可用 Agent 中最可能推进任务的角色。",
                replan_reason=failure_summary,
            )
        ]

    def _first_enabled_specialist(self, enabled_agents: set[str]) -> str:
        if not enabled_agents:
            return "coder"
        for agent_id in ("coder", "analyst", "tester"):
            if agent_id in enabled_agents:
                return agent_id
        return "coder"

    def _resolve_suggested_agent(self, *, step: PlanStep) -> str:
        title = f"{step.title} {step.description}".lower()
        if step.tool_name in {"list_dir", "read_file", "file_search", "retrieve_docs"}:
            return "analyst"
        if step.tool_name == "shell_run":
            return "tester"
        if step.tool_name in {"write_file", "replace_in_file", "multi_file_patch"}:
            return "coder"
        if any(keyword in title for keyword in ("总结", "汇总", "概述", "summary", "summarize", "overview")):
            return "analyst"
        return step.suggested_agent or self._suggest_agent(step)

    def _infer_step_type(self, step: PlanStep) -> str:
        text = f"{step.title} {step.description} {step.tool_name or ''}".lower()
        if any(keyword in text for keyword in ("测试", "验证", "pytest", "test", "shell_run")):
            return "testing"
        if any(keyword in text for keyword in ("总结", "汇总", "概述", "summary", "summarize", "overview")):
            return "analysis"
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
        if any(keyword in title for keyword in ("总结", "汇总", "概述", "summary", "summarize", "overview")):
            return "analyst"
        if "测试" in title or "test" in title:
            return "tester"
        if "分析" in title or "查看" in title or "search" in title:
            return "analyst"
        return "coder"
