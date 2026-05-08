"""Trace 展示器。"""

from __future__ import annotations

import json

from app.contracts.trace import TraceEvent
from app.trace.repository import SQLiteTraceRepository


def format_timeline(events: list[TraceEvent]) -> str:
    """将事件时间线格式化为可读文本。"""
    lines: list[str] = []
    for event in events:
        payload = json.dumps(event.payload, ensure_ascii=False, sort_keys=True)
        line = (
            f"[{event.created_at}] {event.event_type} | run_id={event.run_id} | {event.message} | payload={payload}"
        )
        extras = _format_v3_trace_extras(event)
        if extras:
            line = f"{line}\n{extras}"
        lines.append(line)
    return "\n".join(lines)


def load_and_format_timeline(repository: SQLiteTraceRepository, run_id: str) -> str:
    """按 run_id 加载并格式化时间线。"""
    events = repository.query_timeline(run_id)
    if not events:
        raise ValueError(f"未找到 run_id={run_id} 的 trace。")
    return format_timeline(events)


def load_and_format_root_timeline(repository: SQLiteTraceRepository, root_run_id: str) -> str:
    """按 root_run_id 加载并格式化整棵运行树时间线。"""
    events = repository.query_timeline_by_root(root_run_id)
    if not events:
        raise ValueError(f"未找到 root_run_id={root_run_id} 的 trace。")
    return format_timeline(events)


def load_and_format_session_timeline(repository: SQLiteTraceRepository, session_id: str) -> str:
    """按 session_id 加载并格式化整段会话时间线。"""
    events = repository.query_timeline_by_session(session_id)
    if not events:
        raise ValueError(f"未找到 session_id={session_id} 的 trace。")
    return format_timeline(events)


def _format_v3_trace_extras(event: TraceEvent) -> str:
    if event.event_type == "trigger_skipped":
        return _format_trigger_skipped(event)
    if event.event_type != "graph_finished":
        return ""
    payload = event.payload
    if not isinstance(payload, dict):
        return ""
    shared_state = payload.get("shared_state")
    if not isinstance(shared_state, dict):
        return ""
    planning = shared_state.get("planning")
    if not isinstance(planning, dict) or not planning:
        return ""

    lines = ["  planning:"]
    if planning.get("goal_kind"):
        lines.append(f"    goal_kind={planning['goal_kind']}")
    if planning.get("repo_profile"):
        lines.append(f"    repo_profile={planning['repo_profile']}")
    if planning.get("recovery_strategy"):
        lines.append(f"    recovery_strategy={planning['recovery_strategy']}")
    if planning.get("template_name"):
        lines.append(f"    template_name={planning['template_name']}")
    if planning.get("template_reason"):
        lines.append(f"    template_reason={planning['template_reason']}")
    execution_layers = planning.get("execution_layers")
    if isinstance(execution_layers, list) and execution_layers:
        lines.append(f"    execution_layers={execution_layers}")
    recovery_summary = _format_recovery_branch_summary(payload)
    if recovery_summary:
        lines.append("  recovery:")
        lines.extend(f"    {line}" for line in recovery_summary)
    trigger_governance = _format_trigger_governance(payload)
    if trigger_governance:
        lines.append("  trigger_governance:")
        lines.extend(f"    {line}" for line in trigger_governance)
    return "\n".join(lines)


def _format_recovery_branch_summary(payload: dict[str, object]) -> list[str]:
    execution_nodes = payload.get("execution_nodes")
    if not isinstance(execution_nodes, list):
        return []
    for node in execution_nodes:
        if not isinstance(node, dict):
            continue
        output_data = node.get("output_data")
        if not isinstance(output_data, dict):
            continue
        branch = output_data.get("verification_branch_summary")
        if not isinstance(branch, dict):
            continue
        failed_stage = branch.get("failed_stage")
        if not failed_stage:
            continue
        lines = [f"failed_stage={failed_stage}"]
        focused_passed = branch.get("focused_commands_passed")
        if isinstance(focused_passed, list) and focused_passed:
            lines.append(f"focused_commands_passed={focused_passed}")
        failed_command = branch.get("failed_command")
        if failed_command:
            lines.append(f"failed_command={failed_command}")
        return lines
    return []


def _format_trigger_governance(payload: dict[str, object]) -> list[str]:
    execution_nodes = payload.get("execution_nodes")
    if not isinstance(execution_nodes, list):
        return []
    lines: list[str] = []
    for node in execution_nodes:
        if not isinstance(node, dict) or node.get("kind") != "trigger":
            continue
        output_data = node.get("output_data")
        if not isinstance(output_data, dict):
            continue
        governance = output_data.get("trigger_governance")
        if not isinstance(governance, dict):
            continue
        node_id = node.get("node_id") or "trigger"
        lines.append(
            f"{node_id}: dedupe_key={governance.get('dedupe_key')} cooldown_key={governance.get('cooldown_key')} cooldown_seconds={governance.get('cooldown_seconds')}"
        )
    return lines


def _format_trigger_skipped(event: TraceEvent) -> str:
    payload = event.payload
    if not isinstance(payload, dict):
        return ""
    event_payload = payload.get("payload")
    if not isinstance(event_payload, dict):
        return ""
    lines = ["  trigger_skip:"]
    if event_payload.get("trigger_rule_id"):
        lines.append(f"    rule_id={event_payload['trigger_rule_id']}")
    if event_payload.get("skip_reason"):
        lines.append(f"    skip_reason={event_payload['skip_reason']}")
    if event_payload.get("dedupe_key") is not None:
        lines.append(f"    dedupe_key={event_payload.get('dedupe_key')}")
    if event_payload.get("cooldown_key") is not None:
        lines.append(f"    cooldown_key={event_payload.get('cooldown_key')}")
    if event_payload.get("cooldown_seconds") is not None:
        lines.append(f"    cooldown_seconds={event_payload.get('cooldown_seconds')}")
    return "\n".join(lines)
