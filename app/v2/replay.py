"""V2 replay and presentation helpers."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def build_execution_log(
    *,
    trace: list[dict[str, Any]],
    delegations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a presentation-friendly execution log."""
    delegation_by_task = {
        str(item.get("task_id")): item for item in delegations if item.get("task_id")
    }
    execution_log: list[dict[str, Any]] = []
    for index, event in enumerate(trace, start=1):
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}
        task_id = payload.get("task_id")
        delegation = delegation_by_task.get(str(task_id)) if task_id is not None else None
        execution_log.append(
            {
                "sequence": index,
                "timestamp": event.get("created_at"),
                "event_type": event.get("event_type"),
                "actor": event.get("actor") or "system",
                "action": event.get("action"),
                "status": event.get("status"),
                "message": event.get("message"),
                "input_summary": event.get("input_summary"),
                "output_summary": event.get("output_summary"),
                "step_id": payload.get("step_id"),
                "task_id": task_id,
                "target_agent": payload.get("target_agent"),
                "delegation_id": delegation.get("delegation_id") if delegation else None,
            }
        )
    return execution_log


def build_delegation_tree(
    delegations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a simple delegation tree grouped by step."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for delegation in delegations:
        step_key = str(delegation.get("step_id") or "unscoped")
        grouped[step_key].append(delegation)

    tree: list[dict[str, Any]] = []
    for step_id, items in grouped.items():
        ordered_items = sorted(
            items,
            key=lambda item: (str(item.get("started_at") or ""), str(item.get("delegation_id") or "")),
        )
        tree.append(
            {
                "step_id": None if step_id == "unscoped" else step_id,
                "children": [
                    {
                        "delegation_id": item.get("delegation_id"),
                        "parent_agent_id": item.get("parent_agent_id"),
                        "target_agent": item.get("target_agent"),
                        "task_id": item.get("task_id"),
                        "status": item.get("status"),
                        "summary": item.get("summary"),
                        "error_message": item.get("error_message"),
                        "started_at": item.get("started_at"),
                        "finished_at": item.get("finished_at"),
                    }
                    for item in ordered_items
                ],
            }
        )
    return sorted(tree, key=lambda item: str(item.get("step_id") or ""))


def build_teaching_view(
    *,
    run: dict[str, Any] | None,
    workspace: dict[str, Any] | None,
    execution_log: list[dict[str, Any]],
    delegation_tree: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a concise replay payload for teaching/demo usage."""
    key_takeaways: list[str] = []
    if workspace:
        project_summary = str(workspace.get("project_summary") or "").strip()
        latest_patch_summary = str(workspace.get("latest_patch_summary") or "").strip()
        latest_test_result = workspace.get("latest_test_result") or {}
        if project_summary:
            key_takeaways.append(f"项目分析：{project_summary}")
        if latest_patch_summary:
            key_takeaways.append(f"代码改动：{latest_patch_summary}")
        if isinstance(latest_test_result, dict) and latest_test_result.get("summary"):
            key_takeaways.append(f"测试结果：{latest_test_result['summary']}")
    if run and run.get("final_output"):
        key_takeaways.append(f"最终结论：{run['final_output']}")
    return {
        "run_status": run.get("status") if run else None,
        "step_count": run.get("step_count") if run else 0,
        "delegation_count": sum(len(item["children"]) for item in delegation_tree),
        "event_count": len(execution_log),
        "key_takeaways": key_takeaways,
    }


def build_execution_nodes(
    *,
    run: dict[str, Any] | None,
    workspace: dict[str, Any] | None,
    execution_log: list[dict[str, Any]],
    delegation_tree: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build execution nodes for richer replay consumers."""
    nodes: list[dict[str, Any]] = []
    if run is not None:
        nodes.append(
            {
                "node_id": f"run:{run.get('run_id')}",
                "node_type": "run",
                "label": run.get("task", run.get("run_id")),
                "status": run.get("status"),
                "metadata": {
                    "step_count": run.get("step_count"),
                    "final_output": run.get("final_output"),
                },
            }
        )
    if workspace is not None:
        nodes.append(
            {
                "node_id": f"workspace:{workspace.get('run_id')}",
                "node_type": "workspace",
                "label": "shared-workspace",
                "status": "available",
                "metadata": {
                    "project_summary": workspace.get("project_summary"),
                    "latest_patch_summary": workspace.get("latest_patch_summary"),
                },
            }
        )
    for tree_node in delegation_tree:
        step_id = tree_node.get("step_id") or "unscoped"
        nodes.append(
            {
                "node_id": f"step:{step_id}",
                "node_type": "step",
                "label": step_id,
                "status": "completed",
                "metadata": {
                    "delegation_count": len(tree_node.get("children", [])),
                },
            }
        )
        for child in tree_node.get("children", []):
            if not isinstance(child, dict):
                continue
            nodes.append(
                {
                    "node_id": f"delegation:{child.get('delegation_id')}",
                    "node_type": "delegation",
                    "label": f"{child.get('parent_agent_id')} -> {child.get('target_agent')}",
                    "status": child.get("status"),
                    "metadata": {
                        "task_id": child.get("task_id"),
                        "summary": child.get("summary"),
                    },
                }
            )
    for artifact in artifacts:
        nodes.append(
            {
                "node_id": f"artifact:{artifact.get('artifact_id')}",
                "node_type": "artifact",
                "label": f"{artifact.get('key')}@v{artifact.get('version')}",
                "status": "available",
                "metadata": {
                    "type": artifact.get("type"),
                    "summary": artifact.get("summary"),
                    "producer_agent": artifact.get("producer_agent"),
                },
            }
        )
    for entry in execution_log:
        nodes.append(
            {
                "node_id": f"event:{entry.get('sequence')}",
                "node_type": "event",
                "label": entry.get("event_type"),
                "status": entry.get("status"),
                "metadata": {
                    "actor": entry.get("actor"),
                    "message": entry.get("message"),
                },
            }
        )
    return nodes
