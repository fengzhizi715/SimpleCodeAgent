"""Build product-facing runtime summaries from V3 reports and trace."""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.v3.contracts.runtime_view_contracts import (
    V3FlowCardView,
    V3GovernanceExplainItem,
    V3GovernanceSummary,
    V3RunModeView,
    V3RuntimeSummary,
)


_RUN_MODE_SPECS: dict[str, tuple[str, str]] = {
    "graph_only": ("Graph Only", "本次运行只走了主 graph，没有进入 trigger 或 follow-up 路径。"),
    "graph_trigger": ("Graph + Trigger", "本次运行进入了 event -> trigger -> follow-up 的 runtime 路径。"),
    "graph_autonomy_follow_up": (
        "Graph + Autonomy Follow-up",
        "本次运行在 graph 之后进入了受控 autonomy follow-up 路径。",
    ),
    "graph_governance_intercept": (
        "Graph + Governance Intercept",
        "本次运行命中了 runtime follow-up，但被 governance 规则拦截或冷却。",
    ),
}

_GOVERNANCE_LABELS: dict[str, tuple[str, str]] = {
    "allowed": ("Allowed", "允许继续执行"),
    "blocked": ("Blocked", "被治理规则拦截"),
    "cooled_down": ("Cooled Down", "命中 cooldown，暂不继续执行"),
    "propagation_limited": ("Propagation Limited", "传播深度或连续命中受限"),
    "budget_exhausted": ("Budget Exhausted", "已触达 trigger 或 event 预算上限"),
}


def build_v3_runtime_summary(
    *,
    report: dict[str, Any] | None,
    trace_events: list[dict[str, Any]] | None,
    task: str | None = None,
) -> V3RuntimeSummary | None:
    """Build one stable V3 runtime summary for UI pages."""
    if not isinstance(report, dict):
        return None

    execution_nodes = [
        item for item in report.get("execution_nodes", [])
        if isinstance(item, dict)
    ]
    diagnostics = [
        item for item in report.get("trigger_diagnostics", [])
        if isinstance(item, dict)
    ]
    trace_items = _extract_v3_trace_items(trace_events if isinstance(trace_events, list) else [])
    flow_cards = _build_flow_cards(
        diagnostics=diagnostics,
        execution_nodes=execution_nodes,
        trace_items=trace_items,
    )
    governance_items = _build_governance_items(diagnostics=diagnostics)
    if not governance_items:
        governance_items = _build_governance_items_from_trace(trace_items)
    run_mode_id = _resolve_run_mode_id(
        execution_nodes=execution_nodes,
        flow_cards=flow_cards,
        governance_items=governance_items,
        trace_items=trace_items,
    )
    mode_label, description = _RUN_MODE_SPECS[run_mode_id]
    trace_events = trace_events if isinstance(trace_events, list) else []

    return V3RuntimeSummary(
        run_mode=V3RunModeView(id=run_mode_id, label=mode_label, description=description),
        flow_cards=flow_cards,
        governance_summary=V3GovernanceSummary(
            status_counts=_build_status_counts(governance_items),
            items=governance_items,
        ),
        demo_scenarios=_build_demo_scenarios(
            flow_cards=flow_cards,
            governance_items=governance_items,
            execution_nodes=execution_nodes,
            task=task,
            trace_events=trace_items,
        ),
    )


def _build_flow_cards(
    *,
    diagnostics: list[dict[str, Any]],
    execution_nodes: list[dict[str, Any]],
    trace_items: list[dict[str, Any]],
) -> list[V3FlowCardView]:
    trigger_nodes = [item for item in execution_nodes if str(item.get("kind") or "") == "trigger"]
    cards: list[V3FlowCardView] = []
    for diagnostic in diagnostics:
        rule_id = str(diagnostic.get("trigger_rule_id") or "").strip()
        event_type = str(diagnostic.get("source_event_type") or "").strip()
        follow_up = str(diagnostic.get("target_skill_name") or "").strip() or "follow-up"
        status = str(diagnostic.get("status") or "").strip().lower() or "unknown"
        matched_node = next(
            (
                node for node in trigger_nodes
                if str(node.get("trigger_rule_id") or "") == rule_id
                and str(node.get("skill_name") or "") == follow_up
            ),
            None,
        )
        governance_status = _classify_governance_status(status=status, skip_reason=diagnostic.get("skip_reason"))
        governance_label = _governance_label(governance_status)
        result_label = "Executed" if status == "executed" else "Skipped"
        summary = ""
        if isinstance(matched_node, dict) and str(matched_node.get("summary") or "").strip():
            summary = str(matched_node.get("summary")).strip()
        elif status == "skipped":
            summary = str(diagnostic.get("skip_reason") or "trigger skipped")
        cards.append(
            V3FlowCardView(
                event_type=event_type or "event",
                trigger_rule_id=rule_id or "__unknown__",
                follow_up_label=follow_up,
                result_label=result_label,
                governance_label=governance_label,
                stop_reason=str(diagnostic.get("skip_reason") or "") or None,
                source_event_id=str(diagnostic.get("source_event_id") or "") or None,
                summary=summary,
            )
        )
    if cards:
        return cards
    return _build_flow_cards_from_trace(trace_items)


def _build_governance_items(*, diagnostics: list[dict[str, Any]]) -> list[V3GovernanceExplainItem]:
    items: list[V3GovernanceExplainItem] = []
    for diagnostic in diagnostics:
        status = _classify_governance_status(
            status=str(diagnostic.get("status") or "").strip().lower(),
            skip_reason=diagnostic.get("skip_reason"),
        )
        label, reason = _GOVERNANCE_LABELS[status]
        detail = _governance_detail(status=status, diagnostic=diagnostic)
        items.append(
            V3GovernanceExplainItem(
                status=status,
                label=label,
                reason=reason,
                rule_id=str(diagnostic.get("trigger_rule_id") or "") or None,
                event_type=str(diagnostic.get("source_event_type") or "") or None,
                detail=detail,
            )
        )
    return items


def _build_governance_items_from_trace(trace_items: list[dict[str, Any]]) -> list[V3GovernanceExplainItem]:
    items: list[V3GovernanceExplainItem] = []
    for item in trace_items:
        event_type = str(item.get("event_type") or "").strip().lower()
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        governance = metadata.get("governance_decision")
        if not isinstance(governance, dict):
            continue
        if event_type != "trigger_skipped" and governance.get("skip_reason") is None:
            continue
        status = _classify_governance_status(
            status="skipped" if event_type == "trigger_skipped" else str(item.get("status") or ""),
            skip_reason=governance.get("skip_reason"),
        )
        label, reason = _GOVERNANCE_LABELS[status]
        items.append(
            V3GovernanceExplainItem(
                status=status,
                label=label,
                reason=reason,
                rule_id=str(item.get("trigger_rule_id") or item.get("payload", {}).get("trigger_rule_id") or "") or None,
                event_type=str(item.get("payload", {}).get("source_event_type") or item.get("event_type") or "") or None,
                detail=_format_governance_trace_detail(governance),
            )
        )
    return items


def _build_status_counts(items: list[V3GovernanceExplainItem]) -> dict[str, int]:
    counts = Counter(item.status for item in items)
    counts["blocked"] += sum(1 for item in items if item.status != "allowed")
    return dict(counts)


def _build_flow_cards_from_trace(trace_items: list[dict[str, Any]]) -> list[V3FlowCardView]:
    cards: list[V3FlowCardView] = []
    for item in trace_items:
        event_type = str(item.get("event_type") or "").strip().lower()
        payload = item.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        if event_type not in {"skill_started", "skill_finished", "skill_failed", "trigger_skipped"}:
            continue
        rule_id = str(item.get("trigger_rule_id") or payload.get("trigger_rule_id") or "").strip()
        source_event_type = str(payload.get("source_event_type") or "").strip()
        if not rule_id or not source_event_type:
            continue
        governance = item.get("metadata", {}).get("governance_decision") if isinstance(item.get("metadata"), dict) else {}
        governance_status = _classify_governance_status(
            status="executed" if event_type in {"skill_started", "skill_finished", "skill_failed"} else "skipped",
            skip_reason=payload.get("skip_reason") or (governance.get("skip_reason") if isinstance(governance, dict) else None),
        )
        cards.append(
            V3FlowCardView(
                event_type=source_event_type,
                trigger_rule_id=rule_id,
                follow_up_label=str(item.get("source") or "").strip() or "follow-up",
                result_label="Executed" if event_type != "trigger_skipped" else "Skipped",
                governance_label=_governance_label(governance_status),
                stop_reason=str(payload.get("skip_reason") or "") or None,
                source_event_id=str(item.get("parent_event_id") or "") or None,
                summary=str(payload.get("summary") or payload.get("error") or payload.get("skip_reason") or "").strip(),
            )
        )
    unique_cards: list[V3FlowCardView] = []
    seen: set[tuple[str, str, str]] = set()
    for card in cards:
        key = (card.event_type, card.trigger_rule_id, card.follow_up_label)
        if key in seen:
            continue
        seen.add(key)
        unique_cards.append(card)
    return unique_cards


def _classify_governance_status(*, status: str, skip_reason: object) -> str:
    if status == "executed":
        return "allowed"
    reason = str(skip_reason or "").strip().lower()
    if reason == "cooldown":
        return "cooled_down"
    if reason.startswith("budget_") or reason.startswith("max_triggers_") or reason == "max_trigger_count_per_run":
        return "budget_exhausted"
    if reason in {"max_consecutive_rule_hits", "propagation_limit"} or reason.startswith("propagation_") or reason.startswith("max_depth_"):
        return "propagation_limited"
    return "blocked"


def _governance_label(status: str) -> str:
    return _GOVERNANCE_LABELS.get(status, _GOVERNANCE_LABELS["blocked"])[0]


def _governance_detail(*, status: str, diagnostic: dict[str, Any]) -> str:
    details = diagnostic.get("details")
    if not isinstance(details, dict):
        details = {}
    if status == "allowed":
        priority = details.get("priority")
        cooldown_seconds = details.get("cooldown_seconds")
        fragments = []
        if priority is not None:
            fragments.append(f"priority={priority}")
        if cooldown_seconds is not None:
            fragments.append(f"cooldown={cooldown_seconds}s")
        return " · ".join(fragments) or "Trigger was allowed to continue."
    if status == "cooled_down":
        cooldown_seconds = details.get("cooldown_seconds")
        cooldown_key = details.get("cooldown_key")
        parts = []
        if cooldown_seconds is not None:
            parts.append(f"{cooldown_seconds}s cooldown")
        if cooldown_key:
            parts.append(str(cooldown_key))
        return " · ".join(parts) or "Cooldown active."
    if status == "budget_exhausted":
        limit = details.get("max_trigger_count_per_run") or details.get("rule_count")
        return f"limit={limit}" if limit is not None else "Trigger budget exhausted."
    if status == "propagation_limited":
        consecutive_hits = details.get("consecutive_hits")
        return f"consecutive_hits={consecutive_hits}" if consecutive_hits is not None else "Propagation limited."
    return str(diagnostic.get("skip_reason") or "Governance blocked follow-up.")


def _resolve_run_mode_id(
    *,
    execution_nodes: list[dict[str, Any]],
    flow_cards: list[V3FlowCardView],
    governance_items: list[V3GovernanceExplainItem],
    trace_items: list[dict[str, Any]],
) -> str:
    if any(item.status != "allowed" for item in governance_items):
        return "graph_governance_intercept"
    if any(str(node.get("node_id") or "").startswith("autonomy:") for node in execution_nodes) or any(
        str(item.get("source") or "").startswith("autonomy:") for item in trace_items
    ):
        return "graph_autonomy_follow_up"
    if flow_cards or any(str(node.get("kind") or "") == "trigger" for node in execution_nodes) or any(
        str(item.get("trigger_rule_id") or "").strip() for item in trace_items
    ):
        return "graph_trigger"
    return "graph_only"


def _build_demo_scenarios(
    *,
    flow_cards: list[V3FlowCardView],
    governance_items: list[V3GovernanceExplainItem],
    execution_nodes: list[dict[str, Any]],
    task: str | None,
    trace_events: list[dict[str, Any]],
) -> list[str]:
    scenarios: list[str] = []
    if any(card.event_type == "test_failed" and card.follow_up_label in {"coding", "tdd", "test_runner"} for card in flow_cards):
        scenarios.append("测试失败 -> 自动补救 -> 再测")
    if any(card.event_type == "code_updated" and card.follow_up_label == "test_runner" for card in flow_cards) or any(
        str(event.get("event_type") or "") == "code_updated" for event in trace_events
    ):
        scenarios.append("代码变更 -> 自动 follow-up test")
    if any(item.status != "allowed" for item in governance_items):
        scenarios.append("事件命中但被 governance 拦截")
    return scenarios


def _extract_v3_trace_items(trace_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for event in trace_events:
        payload = event.get("payload")
        if isinstance(payload, dict) and payload.get("event_type") and payload.get("source"):
            items.append(payload)
    return items


def _format_governance_trace_detail(governance: dict[str, Any]) -> str:
    if governance.get("skip_reason") == "cooldown":
        cooldown = governance.get("cooldown_seconds")
        return f"{cooldown}s cooldown" if cooldown is not None else "Cooldown active."
    if governance.get("max_trigger_count_per_run") is not None:
        return f"max_count={governance.get('max_trigger_count_per_run')}"
    return str(governance.get("skip_reason") or "Governance intercepted.")
