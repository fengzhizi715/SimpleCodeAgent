"""Autonomy runtime for V3.2 Controlled Autonomy."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.v3.contracts.agent_message_contracts import AgentMessage, AgentMessageType
from app.v3.contracts.audit_contracts import (
    AuditAction,
    AuditRecord,
    DecisionTrace,
    GovernanceAction,
)
from app.v3.contracts.autonomy_contracts import (
    AutonomyBudget,
    AutonomyDecision,
    AutonomyRequest,
    AutonomyTaskType,
)
from app.v3.contracts.event_contracts import EventType, V3Event
from app.v3.contracts.execution_contracts import ExecutionNode
from app.v3.contracts.skill_contracts import SkillInput
from app.v3.events.event_bus import EventBus
from app.v3.events.event_store import EventStore
from app.v3.governance.circuit_breaker import CircuitBreakerManager
from app.v3.governance.execution_budget import ExecutionBudgetState
from app.v3.governance.propagation_limit import PropagationState
from app.v3.runtime.skill_executor import SkillExecutor


class AutonomyRuntime:
    """Controlled autonomy layer that creates and governs task requests.

    This is not a second runtime independent of the ExecutionKernel.
    It operates on top of the existing event -> governance -> execution
    chain and only solves one problem:

    When certain conditions are met, the system can proactively propose
    a controlled execution request. After governance evaluation, this
    request becomes a skill execution or a small graph execution.
    """

    def __init__(
        self,
        skill_executor: SkillExecutor,
        event_bus: EventBus | None = None,
        event_store: EventStore | None = None,
        execution_nodes: list[ExecutionNode] | None = None,
        messages: list[AgentMessage] | None = None,
        budget: ExecutionBudgetState | None = None,
        propagation: PropagationState | None = None,
        circuit_breaker: CircuitBreakerManager | None = None,
    ) -> None:
        self.skill_executor = skill_executor
        self.event_bus = event_bus
        self.event_store = event_store
        self.execution_nodes = execution_nodes
        self.messages = messages
        self.budget = budget
        self.propagation = propagation
        self.circuit_breaker = circuit_breaker or CircuitBreakerManager()

        self._requests: list[AutonomyRequest] = []
        self._decisions: list[AutonomyDecision] = []
        self._audit_records: list[AuditRecord] = []
        self._decision_traces: list[DecisionTrace] = []
        self._governance_actions: list[GovernanceAction] = []

    @property
    def requests(self) -> list[AutonomyRequest]:
        return list(self._requests)

    @property
    def decisions(self) -> list[AutonomyDecision]:
        return list(self._decisions)

    @property
    def audit_records(self) -> list[AuditRecord]:
        return list(self._audit_records)

    @property
    def decision_traces(self) -> list[DecisionTrace]:
        return list(self._decision_traces)

    @property
    def governance_actions(self) -> list[GovernanceAction]:
        return list(self._governance_actions)

    async def create_follow_up_request(
        self,
        *,
        run_id: str,
        target_skill_name: str,
        reason: str,
        source_event_id: str | None = None,
        source_trigger_rule_id: str | None = None,
        payload: dict[str, Any] | None = None,
        max_iterations: int = 1,
        stop_condition: str | None = None,
        budget: AutonomyBudget | None = None,
    ) -> AutonomyRequest:
        request = AutonomyRequest(
            request_id=str(uuid4()),
            run_id=run_id,
            task_type=AutonomyTaskType.FOLLOW_UP,
            target_skill_name=target_skill_name,
            reason=reason,
            source_event_id=source_event_id,
            source_trigger_rule_id=source_trigger_rule_id,
            payload=payload or {},
            max_iterations=max_iterations,
            stop_condition=stop_condition,
            budget=budget,
        )
        self._requests.append(request)
        self._record_audit(
            run_id=run_id,
            action=AuditAction.AUTONOMY_REQUEST_CREATED,
            actor="autonomy_runtime",
            target=request.request_id,
            reason=reason,
            summary=f"Created follow-up request for {target_skill_name}",
            details={
                "request_id": request.request_id,
                "task_type": request.task_type.value,
                "source_event_id": source_event_id,
            },
        )
        return request

    async def create_scheduled_check_request(
        self,
        *,
        run_id: str,
        target_skill_name: str,
        reason: str,
        payload: dict[str, Any] | None = None,
        budget: AutonomyBudget | None = None,
    ) -> AutonomyRequest:
        request = AutonomyRequest(
            request_id=str(uuid4()),
            run_id=run_id,
            task_type=AutonomyTaskType.SCHEDULED_CHECK,
            target_skill_name=target_skill_name,
            reason=reason,
            payload=payload or {},
            budget=budget,
        )
        self._requests.append(request)
        self._record_audit(
            run_id=run_id,
            action=AuditAction.AUTONOMY_REQUEST_CREATED,
            actor="autonomy_runtime",
            target=request.request_id,
            reason=reason,
            summary=f"Created scheduled check request for {target_skill_name}",
            details={
                "request_id": request.request_id,
                "task_type": request.task_type.value,
            },
        )
        return request

    async def create_retry_request(
        self,
        *,
        run_id: str,
        target_skill_name: str,
        reason: str,
        source_event_id: str | None = None,
        payload: dict[str, Any] | None = None,
        budget: AutonomyBudget | None = None,
    ) -> AutonomyRequest:
        request = AutonomyRequest(
            request_id=str(uuid4()),
            run_id=run_id,
            task_type=AutonomyTaskType.RETRY,
            target_skill_name=target_skill_name,
            reason=reason,
            source_event_id=source_event_id,
            payload=payload or {},
            budget=budget,
        )
        self._requests.append(request)
        self._record_audit(
            run_id=run_id,
            action=AuditAction.AUTONOMY_REQUEST_CREATED,
            actor="autonomy_runtime",
            target=request.request_id,
            reason=reason,
            summary=f"Created retry request for {target_skill_name}",
            details={
                "request_id": request.request_id,
                "task_type": request.task_type.value,
                "source_event_id": source_event_id,
            },
        )
        return request

    async def evaluate_request(self, request: AutonomyRequest) -> AutonomyDecision:
        approved, reason, factors = self._evaluate_governance(request)

        decision = AutonomyDecision(
            request_id=request.request_id,
            run_id=request.run_id,
            approved=approved,
            reason=reason,
            applied_budget=request.budget,
            metadata={"factors": factors},
        )
        self._decisions.append(decision)

        action_type = (
            AuditAction.AUTONOMY_REQUEST_APPROVED
            if approved
            else AuditAction.AUTONOMY_REQUEST_REJECTED
        )
        self._record_audit(
            run_id=request.run_id,
            event_id=request.source_event_id,
            action=action_type,
            actor="autonomy_governance",
            target=request.request_id,
            reason=reason,
            summary=f"{'Approved' if approved else 'Rejected'} autonomy request for {request.target_skill_name}",
            details={
                "request_id": request.request_id,
                "approved": approved,
                "factors": factors,
            },
        )

        self._decision_traces.append(
            DecisionTrace(
                run_id=request.run_id,
                event_id=request.source_event_id,
                decision_type="autonomy_evaluation",
                approved=approved,
                reason=reason,
                factors=factors,
                summary=f"Autonomy request {request.request_id} {'approved' if approved else 'rejected'}: {reason}",
            )
        )

        return decision

    async def execute_approved_request(
        self,
        request: AutonomyRequest,
        decision: AutonomyDecision,
    ) -> dict[str, Any]:
        if not decision.approved:
            return {
                "success": False,
                "error": f"Request {request.request_id} was not approved: {decision.reason}",
            }

        run_id = request.run_id

        if self.budget is not None and self.budget.any_exhausted:
            reasons = self.budget.get_exhaustion_reasons()
            self._record_audit(
                run_id=run_id,
                action=AuditAction.BUDGET_EXHAUSTED,
                actor="execution_budget",
                target=request.request_id,
                reason="; ".join(reasons),
                summary="Execution budget exhausted, cannot execute autonomy request",
                details={"request_id": request.request_id, "budget": self.budget.to_dict()},
            )
            return {
                "success": False,
                "error": f"Budget exhausted: {'; '.join(reasons)}",
            }

        if self.propagation is not None and self.propagation.autonomy_tasks_exceeded:
            reasons = self.propagation.get_exhaustion_reasons()
            self._record_audit(
                run_id=run_id,
                action=AuditAction.PROPAGATION_LIMIT_REACHED,
                actor="propagation_limit",
                target=request.request_id,
                reason="; ".join(reasons),
                summary="Propagation limit reached, cannot execute autonomy request",
                details={"request_id": request.request_id, "propagation": self.propagation.to_dict()},
            )
            return {
                "success": False,
                "error": f"Propagation limit reached: {'; '.join(reasons)}",
            }

        if self.circuit_breaker.is_open(request.target_skill_name):
            state = self.circuit_breaker.get_state(request.target_skill_name)
            self._record_audit(
                run_id=run_id,
                action=AuditAction.CIRCUIT_BREAKER_OPENED,
                actor="circuit_breaker",
                target=request.target_skill_name,
                reason=f"Circuit breaker open for {request.target_skill_name}",
                summary="Circuit breaker preventing execution",
                details={"request_id": request.request_id, "circuit_state": state},
            )
            return {
                "success": False,
                "error": f"Circuit breaker open for {request.target_skill_name}",
            }

        if self.propagation is not None:
            if not self.propagation.consume_autonomy_task():
                self._record_audit(
                    run_id=run_id,
                    action=AuditAction.TASK_STOPPED,
                    actor="propagation_limit",
                    target=request.request_id,
                    reason="Autonomy task limit reached during execution",
                    summary="Stopped autonomy task due to propagation limit",
                    details={"request_id": request.request_id},
                )
                return {"success": False, "error": "Autonomy task limit reached"}

        self._record_audit(
            run_id=run_id,
            action=AuditAction.TASK_CREATED,
            actor="autonomy_runtime",
            target=request.request_id,
            reason=request.reason,
            summary=f"Executing autonomy task: {request.target_skill_name}",
            details={"request_id": request.request_id, "task_type": request.task_type.value},
        )

        await self._publish_event(
            V3Event(
                run_id=run_id,
                event_type=EventType.SKILL_STARTED.value,
                source=f"autonomy:{request.task_type.value}",
                parent_event_id=request.source_event_id,
                execution_chain_id=request.source_event_id,
                trigger_depth=self.propagation.current_depth if self.propagation else 0,
                payload={
                    "autonomy_request_id": request.request_id,
                    "task_type": request.task_type.value,
                    "reason": request.reason,
                    "input_payload": request.payload,
                },
                metadata={
                    "autonomy_origin": {
                        "request_id": request.request_id,
                        "task_type": request.task_type.value,
                        "reason": request.reason,
                    },
                    "governance_decision": {
                        "approved": decision.approved,
                        "reason": decision.reason,
                    },
                },
            )
        )

        if self.budget is not None:
            self.budget.consume_step()

        output = await self.skill_executor.execute(
            request.target_skill_name,
            SkillInput(
                run_id=run_id,
                payload=request.payload,
                context={
                    "autonomy_request_id": request.request_id,
                    "task_type": request.task_type.value,
                    "reason": request.reason,
                },
            ),
        )

        await self._publish_event(
            V3Event(
                run_id=run_id,
                event_type=(
                    EventType.SKILL_FINISHED.value
                    if output.success
                    else EventType.SKILL_FAILED.value
                ),
                source=f"autonomy:{request.task_type.value}",
                parent_event_id=request.source_event_id,
                execution_chain_id=request.source_event_id,
                trigger_depth=self.propagation.current_depth if self.propagation else 0,
                payload={
                    "autonomy_request_id": request.request_id,
                    "task_type": request.task_type.value,
                    "summary": output.summary,
                    "error": output.error,
                    "data": output.data,
                },
                metadata={
                    "autonomy_origin": {
                        "request_id": request.request_id,
                        "task_type": request.task_type.value,
                        "reason": request.reason,
                    },
                    "governance_decision": {
                        "approved": decision.approved,
                        "reason": decision.reason,
                    },
                },
            )
        )

        if output.success:
            self.circuit_breaker.record_success(request.target_skill_name)
        else:
            self.circuit_breaker.record_failure(
                request.target_skill_name, output.error
            )

        self._record_audit(
            run_id=run_id,
            action=AuditAction.TASK_EXECUTED,
            actor=request.target_skill_name,
            target=request.request_id,
            reason=output.summary,
            summary=f"Autonomy task {'succeeded' if output.success else 'failed'}: {output.summary}",
            details={
                "request_id": request.request_id,
                "success": output.success,
                "error": output.error,
            },
        )

        if self.execution_nodes is not None:
            self.execution_nodes.append(
                ExecutionNode(
                    node_id=f"autonomy:{request.request_id}",
                    kind="trigger",
                    skill_name=request.target_skill_name,
                    status="done" if output.success else "failed",
                    source_event_type=EventType.SKILL_STARTED.value,
                    source_event_id=request.source_event_id,
                    summary=output.summary,
                    output_data={
                        **output.data,
                        "autonomy_request_id": request.request_id,
                        "task_type": request.task_type.value,
                    },
                )
            )

        return {
            "success": output.success,
            "summary": output.summary,
            "error": output.error,
            "data": output.data,
        }

    def _evaluate_governance(
        self, request: AutonomyRequest
    ) -> tuple[bool, str, list[dict[str, Any]]]:
        factors: list[dict[str, Any]] = []

        if self.circuit_breaker.is_open(request.target_skill_name):
            state = self.circuit_breaker.get_state(request.target_skill_name)
            factors.append(
                {
                    "factor": "circuit_breaker",
                    "value": "open",
                    "detail": state,
                }
            )
            return False, "Circuit breaker open for target skill", factors

        if self.budget is not None and self.budget.any_exhausted:
            reasons = self.budget.get_exhaustion_reasons()
            factors.append(
                {
                    "factor": "execution_budget",
                    "value": "exhausted",
                    "detail": reasons,
                }
            )
            return False, f"Execution budget exhausted: {'; '.join(reasons)}", factors

        if self.propagation is not None:
            if self.propagation.depth_exceeded:
                factors.append(
                    {
                        "factor": "propagation_depth",
                        "value": "exceeded",
                        "detail": self.propagation.to_dict(),
                    }
                )
                return False, "Propagation depth exceeded", factors

            if self.propagation.autonomy_tasks_exceeded:
                factors.append(
                    {
                        "factor": "autonomy_task_limit",
                        "value": "exceeded",
                        "detail": self.propagation.to_dict(),
                    }
                )
                return False, "Autonomy task limit exceeded", factors

        factors.append({"factor": "governance_check", "value": "passed"})
        return True, "Governance checks passed", factors

    def _record_audit(
        self,
        *,
        run_id: str,
        action: AuditAction,
        actor: str,
        target: str,
        reason: str,
        summary: str,
        event_id: str | None = None,
        execution_chain_id: str | None = None,
        policy_id: str | None = None,
        rule_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditRecord:
        record = AuditRecord(
            run_id=run_id,
            event_id=event_id,
            execution_chain_id=execution_chain_id,
            policy_id=policy_id,
            rule_id=rule_id,
            action=action,
            actor=actor,
            target=target,
            reason=reason,
            summary=summary,
            details=details or {},
        )
        self._audit_records.append(record)
        return record

    async def _publish_event(self, event: V3Event) -> None:
        if self.budget is not None and not self.budget.consume_event():
            return
        if self.event_store is not None:
            self.event_store.append(event)
        if self.event_bus is not None:
            await self.event_bus.publish(event)
