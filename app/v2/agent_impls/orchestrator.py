"""Orchestrator agent identity and policy helpers."""

from __future__ import annotations

from app.contracts.agent import AgentArtifact, AgentResult, AgentSpec, AgentTask, SharedWorkspace
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
    ) -> dict[str, object]:
        """Build a serializable policy snapshot for workspace and trace."""
        return {
            "orchestrator_agent_id": self.spec.agent_id,
            "mode": "centralized",
            "enabled_agents": sorted(enabled_agents),
            "max_steps": max_steps,
            "max_replans": max_replans,
            "run_timeout_seconds": run_timeout_seconds,
            "delegation_model": "orchestrator_only",
            "sub_agent_delegation_allowed": False,
            "review_strategy": review_strategy or {},
        }

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
        )
        summary = "Orchestrator policy snapshot prepared."
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.spec.agent_id,
            status="completed",
            summary=summary,
            output_data={"policy": policy},
            artifacts=[
                AgentArtifact(
                    key="orchestrator_policy",
                    type="policy",
                    summary=summary,
                    producer_agent=self.spec.agent_id,
                    content=policy,
                )
            ],
        )
