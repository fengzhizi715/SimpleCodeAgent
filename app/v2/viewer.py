"""V2 replay viewers."""

from __future__ import annotations


def format_execution_log(entries: list[dict[str, object]]) -> str:
    """Format execution log entries into readable lines."""
    lines: list[str] = []
    for entry in entries:
        lines.append(
            "[{sequence}] {event_type} | actor={actor} | status={status} | message={message}".format(
                sequence=entry.get("sequence", "?"),
                event_type=entry.get("event_type", ""),
                actor=entry.get("actor", "system"),
                status=entry.get("status", ""),
                message=entry.get("message", ""),
            )
        )
    return "\n".join(lines)


def format_delegation_tree(tree: list[dict[str, object]]) -> str:
    """Format delegation tree into readable text."""
    lines: list[str] = []
    for node in tree:
        step_id = node.get("step_id") or "unscoped"
        lines.append(f"step={step_id}")
        for child in node.get("children", []):
            if not isinstance(child, dict):
                continue
            lines.append(
                "  {parent} -> {target} | status={status} | summary={summary}".format(
                    parent=child.get("parent_agent_id", "orchestrator"),
                    target=child.get("target_agent", ""),
                    status=child.get("status", ""),
                    summary=child.get("summary", ""),
                )
            )
    return "\n".join(lines)


def format_execution_nodes(nodes: list[dict[str, object]]) -> str:
    """Format execution nodes into readable text."""
    lines: list[str] = []
    for node in nodes:
        lines.append(
            "{node_type} | {label} | status={status}".format(
                node_type=node.get("node_type", ""),
                label=node.get("label", ""),
                status=node.get("status", ""),
            )
        )
    return "\n".join(lines)
