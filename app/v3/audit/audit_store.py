"""Audit log store for V3.2 Controlled Autonomy."""

from __future__ import annotations

from app.v3.contracts.audit_contracts import (
    AuditAction,
    AuditRecord,
    DecisionTrace,
    GovernanceAction,
    StopReason,
)


class AuditLogStore:
    """In-memory store for audit records, decision traces, governance actions, and stop reasons."""

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []
        self._decision_traces: list[DecisionTrace] = []
        self._governance_actions: list[GovernanceAction] = []
        self._stop_reasons: list[StopReason] = []

    def add_record(self, record: AuditRecord) -> None:
        self._records.append(record)

    def add_decision_trace(self, trace: DecisionTrace) -> None:
        self._decision_traces.append(trace)

    def add_governance_action(self, action: GovernanceAction) -> None:
        self._governance_actions.append(action)

    def add_stop_reason(self, reason: StopReason) -> None:
        self._stop_reasons.append(reason)

    def list_records(self) -> list[AuditRecord]:
        return list(self._records)

    def list_records_by_run_id(self, run_id: str) -> list[AuditRecord]:
        return [r for r in self._records if r.run_id == run_id]

    def list_records_by_action(self, action: AuditAction) -> list[AuditRecord]:
        return [r for r in self._records if r.action == action]

    def list_records_by_event_id(self, event_id: str) -> list[AuditRecord]:
        return [r for r in self._records if r.event_id == event_id]

    def list_records_by_chain_id(self, execution_chain_id: str) -> list[AuditRecord]:
        return [r for r in self._records if r.execution_chain_id == execution_chain_id]

    def list_records_by_policy_id(self, policy_id: str) -> list[AuditRecord]:
        return [r for r in self._records if r.policy_id == policy_id]

    def list_records_by_rule_id(self, rule_id: str) -> list[AuditRecord]:
        return [r for r in self._records if r.rule_id == rule_id]

    def list_records_by_time_range(
        self, start: str | None = None, end: str | None = None
    ) -> list[AuditRecord]:
        results = self._records
        if start is not None:
            results = [r for r in results if r.created_at.isoformat() >= start]
        if end is not None:
            results = [r for r in results if r.created_at.isoformat() <= end]
        return results

    def list_decision_traces(self) -> list[DecisionTrace]:
        return list(self._decision_traces)

    def list_decision_traces_by_run_id(self, run_id: str) -> list[DecisionTrace]:
        return [t for t in self._decision_traces if t.run_id == run_id]

    def list_decision_traces_by_event_id(self, event_id: str) -> list[DecisionTrace]:
        return [t for t in self._decision_traces if t.event_id == event_id]

    def list_decision_traces_by_chain_id(self, execution_chain_id: str) -> list[DecisionTrace]:
        return [t for t in self._decision_traces if t.execution_chain_id == execution_chain_id]

    def list_governance_actions(self) -> list[GovernanceAction]:
        return list(self._governance_actions)

    def list_governance_actions_by_run_id(self, run_id: str) -> list[GovernanceAction]:
        return [a for a in self._governance_actions if a.run_id == run_id]

    def list_stop_reasons(self) -> list[StopReason]:
        return list(self._stop_reasons)

    def list_stop_reasons_by_run_id(self, run_id: str) -> list[StopReason]:
        return [s for s in self._stop_reasons if s.run_id == run_id]

    def list_stop_reasons_by_type(self, reason_type: str) -> list[StopReason]:
        return [s for s in self._stop_reasons if s.reason_type == reason_type]

    def get_audit_summary(self, run_id: str) -> dict[str, object]:
        records = self.list_records_by_run_id(run_id)
        action_counts: dict[str, int] = {}
        for r in records:
            action_counts[r.action.value] = action_counts.get(r.action.value, 0) + 1

        decisions = self.list_decision_traces_by_run_id(run_id)
        approved_count = sum(1 for d in decisions if d.approved)
        rejected_count = len(decisions) - approved_count

        stop_reasons = self.list_stop_reasons_by_run_id(run_id)
        stop_type_counts: dict[str, int] = {}
        for s in stop_reasons:
            stop_type_counts[s.reason_type] = stop_type_counts.get(s.reason_type, 0) + 1

        return {
            "run_id": run_id,
            "total_audit_records": len(records),
            "action_counts": action_counts,
            "total_decisions": len(decisions),
            "approved_decisions": approved_count,
            "rejected_decisions": rejected_count,
            "total_governance_actions": len(
                self.list_governance_actions_by_run_id(run_id)
            ),
            "total_stop_reasons": len(stop_reasons),
            "stop_type_counts": stop_type_counts,
        }
