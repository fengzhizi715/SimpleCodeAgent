"""Orchestrator agent identity, prompt, and policy helpers."""

from __future__ import annotations

from app.contracts.agent import AgentArtifact, AgentResult, AgentSpec, AgentTask, SharedWorkspace
from app.contracts.planner import PlanStep
from app.v2.base import AgentBase, AgentContext


class OrchestratorAgent(AgentBase):
    """Represent the centralized V2 orchestrator as an Agent identity.

    The runtime still owns the execution loop. This class makes the
    orchestrator visible to the registry, trace payloads, UI catalog, and
    future prompt/policy evolution without giving sub agents delegation power.
    """

    def __init__(self) -> None:
        super().__init__(
            AgentSpec(
                agent_id="orchestrator",
                role="orchestrator",
                description="Centralized coordinator that plans, delegates, retries, replans, and summarizes V2 runs.",
                capabilities=[
                    "centralized-scheduling",
                    "delegation-control",
                    "workspace-governance",
                    "retry-replan-fallback",
                    "trace-coordination",
                ],
            )
        )

    def build_run_policy(
        self,
        *,
        enabled_agents: set[str],
        max_steps: int,
        max_replans: int,
        run_timeout_seconds: int,
        review_strategy: dict[str, object] | None,
        external_coding: dict[str, object] | None = None,
        profile_name: str | None = None,
    ) -> dict[str, object]:
        """Build a serializable policy snapshot for workspace and trace."""
        selected_profile = profile_name or self._select_profile(enabled_agents=enabled_agents)
        return {
            "orchestrator_agent_id": self.spec.agent_id,
            "profile_name": selected_profile,
            "mode": "centralized",
            "enabled_agents": sorted(enabled_agents),
            "max_steps": max_steps,
            "max_replans": max_replans,
            "run_timeout_seconds": run_timeout_seconds,
            "delegation_model": "orchestrator_only",
            "sub_agent_delegation_allowed": False,
            "execution_style": self._execution_style(selected_profile),
            "retry_policy": self._retry_policy(max_replans=max_replans),
            "routing_policy": self._routing_policy(enabled_agents=enabled_agents),
            "review_strategy": review_strategy or {},
            "external_coding": external_coding or {},
        }

    def build_system_prompt(self, *, policy: dict[str, object]) -> str:
        """Build the orchestrator system prompt used for teaching and future LLM policies."""
        enabled_agents = ", ".join(str(item) for item in policy.get("enabled_agents", []))
        return "\n".join(
            [
                "You are the Orchestrator Agent for SimpleCodeAgent V2.",
                "You coordinate specialist agents through a centralized delegation model.",
                "You must not perform deep coding, project analysis, or testing by yourself.",
                "You own the execution policy, shared workspace governance, retry/replan decisions, and final synthesis.",
                "Only the orchestrator may delegate tasks. Sub agents cannot delegate to other sub agents.",
                f"Enabled agents: {enabled_agents}.",
                f"Execution style: {policy.get('execution_style')}.",
                f"Retry policy: {policy.get('retry_policy')}.",
                "When a step fails, prefer bounded retry, tester-to-coder feedback, or replan before fail-fast.",
                "Keep trace events explainable: every delegation should have a short reason.",
            ]
        )

    def build_strategy_profile(self, *, policy: dict[str, object]) -> dict[str, object]:
        """Return a compact strategy profile for workspace, trace, and UI replay."""
        enabled_agents = [str(item) for item in policy.get("enabled_agents", [])]
        return {
            "name": str(policy.get("profile_name") or "balanced"),
            "execution_style": policy.get("execution_style"),
            "routing_policy": policy.get("routing_policy", {}),
            "retry_policy": policy.get("retry_policy", {}),
            "enabled_agents": enabled_agents,
            "guardrails": [
                "centralized_delegation_only",
                "bounded_steps",
                "bounded_replans",
                "workspace_state_updates",
                "trace_every_delegation",
            ],
            "review_enabled": "reviewer" in enabled_agents,
            "tester_enabled": "tester" in enabled_agents,
        }

    def explain_plan(self, *, plan_steps: list[PlanStep], policy: dict[str, object]) -> dict[str, object]:
        """Explain why the filtered plan is executable under the current policy."""
        enabled_agents = {str(item) for item in policy.get("enabled_agents", [])}
        explanations = [
            {
                "step_id": step.id,
                "title": step.title,
                "target_agent": step.suggested_agent or "coder",
                "reason": self.explain_delegation(
                    target_agent=step.suggested_agent or "coder",
                    task_goal=step.goal or step.description or step.title,
                    step_type=step.type,
                    policy=policy,
                ),
                "enabled": (step.suggested_agent or "coder") in enabled_agents,
            }
            for step in plan_steps
        ]
        return {
            "summary": f"Orchestrator will execute {len(plan_steps)} plan step(s) using centralized delegation.",
            "steps": explanations,
        }

    def explain_delegation(
        self,
        *,
        target_agent: str,
        task_goal: str,
        step_type: str,
        policy: dict[str, object],
    ) -> str:
        """Explain a single delegation decision."""
        route_reason = {
            "planner": "Planner is responsible for turning the user goal into a structured plan.",
            "analyst": "Analyst is best suited for project structure, key files, and implementation context.",
            "coder": "Coder is responsible for localized code changes using workspace context.",
            "external_coder": "ExternalCoder uses a guarded template command to invoke external coding CLI.",
            "tester": "Tester validates the latest change and turns logs into structured feedback.",
            "reviewer": "Reviewer checks patch risk, maintainability, boundaries, and test-result consistency.",
        }.get(target_agent, "The selected agent matches the step's suggested role.")
        return (
            f"{route_reason} Step type is '{step_type}'. "
            f"Goal: {task_goal}. Policy profile: {policy.get('profile_name', 'balanced')}."
        )

    def run(
        self,
        *,
        task: AgentTask,
        workspace: SharedWorkspace,
        context: AgentContext,
        prompt_context: dict[str, object],
    ) -> AgentResult:
        """Return an identity/policy snapshot.

        OrchestratorRuntime intentionally does not delegate its main loop back
        into this method yet; keeping that loop in runtime avoids a large
        behavioral rewrite while still making the orchestrator a first-class
        agent in contracts and observability.
        """
        policy = self.build_run_policy(
            enabled_agents=set(prompt_context.get("enabled_agents", [])),
            max_steps=int(prompt_context.get("max_steps") or 0),
            max_replans=int(prompt_context.get("max_replans") or 0),
            run_timeout_seconds=int(prompt_context.get("run_timeout_seconds") or 0),
            review_strategy=prompt_context.get("review_strategy")
            if isinstance(prompt_context.get("review_strategy"), dict)
            else None,
            profile_name=str(prompt_context.get("profile_name") or "") or None,
        )
        system_prompt = self.build_system_prompt(policy=policy)
        strategy_profile = self.build_strategy_profile(policy=policy)
        summary = "Orchestrator policy snapshot prepared."
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.spec.agent_id,
            status="completed",
            summary=summary,
            output_data={
                "policy": policy,
                "system_prompt": system_prompt,
                "strategy_profile": strategy_profile,
            },
            artifacts=[
                AgentArtifact(
                    key="orchestrator_policy",
                    type="policy",
                    summary=summary,
                    producer_agent=self.spec.agent_id,
                    content=policy,
                ),
                AgentArtifact(
                    key="orchestrator_strategy_profile",
                    type="policy",
                    summary="Orchestrator strategy profile prepared.",
                    producer_agent=self.spec.agent_id,
                    content=strategy_profile,
                )
            ],
        )

    def _select_profile(self, *, enabled_agents: set[str]) -> str:
        if "tester" not in enabled_agents:
            return "fast_fix"
        if "reviewer" in enabled_agents:
            return "quality_gate"
        return "balanced"

    def _execution_style(self, profile_name: str) -> str:
        styles = {
            "fast_fix": "short_loop_without_required_test_gate",
            "quality_gate": "analysis_code_test_review_when_available",
            "balanced": "analysis_code_test_with_bounded_replan",
        }
        return styles.get(profile_name, styles["balanced"])

    def _retry_policy(self, *, max_replans: int) -> dict[str, object]:
        return {
            "max_replans": max_replans,
            "tester_failure_feedback": "tester_to_coder_once_when_actionable",
            "no_tests_collected": "replan_or_fail_fast",
            "infinite_loop_guard": "max_steps_and_timeout",
        }

    def _routing_policy(self, *, enabled_agents: set[str]) -> dict[str, object]:
        return {
            "planner": "always_enabled",
            "orchestrator": "always_enabled",
            "analysis": "analyst" if "analyst" in enabled_agents else "skip_filtered_steps",
            "coding": "coder" if "coder" in enabled_agents else "skip_filtered_steps",
            "testing": "tester" if "tester" in enabled_agents else "disabled_by_run_config",
            "review": "reviewer" if "reviewer" in enabled_agents else "disabled_by_run_config",
        }
