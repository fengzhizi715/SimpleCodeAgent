"""Run the V3 graph runtime from the command line."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from app.v3 import build_default_skill_registry
from app.v3.contracts.graph_contracts import TaskGraph
from app.v3.contracts.skill_contracts import SkillInput
from app.v3.events.event_bus import EventBus
from app.v3.events.event_store import EventStore
from app.v3.graph.graph_builder import GraphBuilder
from app.v3.graph.graph_validator import GraphValidator
from app.v3.runtime.execution_kernel import ExecutionKernel
from app.v3.runtime.graph_executor import GraphExecutor
from app.v3.runtime.skill_executor import SkillExecutor


def build_parser() -> argparse.ArgumentParser:
    """Build the V3 CLI parser."""
    parser = argparse.ArgumentParser(description="Run the V3 graph-based runtime.")
    parser.add_argument("--goal", dest="goal", default="", help="Goal sent to the planning skill.")
    parser.add_argument(
        "--graph-file",
        dest="graph_file",
        default="",
        help="Optional JSON file containing a TaskGraph payload.",
    )
    return parser


async def main() -> None:
    """Run the V3 CLI flow."""
    args = build_parser().parse_args()
    registry = build_default_skill_registry()
    skill_executor = SkillExecutor(registry)
    event_bus = EventBus()
    event_store = EventStore()
    graph_executor = GraphExecutor(skill_executor, event_bus=event_bus, event_store=event_store)
    kernel = ExecutionKernel(
        graph_executor=graph_executor,
        validator=GraphValidator(),
        event_bus=event_bus,
        event_store=event_store,
    )

    graph = await _resolve_graph(args.goal, args.graph_file, skill_executor)
    result = await kernel.run_graph(graph)
    print(json.dumps(result.to_report(graph).model_dump(mode="json"), ensure_ascii=False, indent=2))


async def _resolve_graph(goal: str, graph_file: str, skill_executor: SkillExecutor) -> TaskGraph:
    if graph_file:
        payload = json.loads(Path(graph_file).read_text(encoding="utf-8"))
        return GraphBuilder().from_payload(payload)
    if not goal.strip():
        raise SystemExit("Either --goal or --graph-file is required.")
    run_id = str(uuid4())
    planning_output = await skill_executor.execute(
        "planning",
        SkillInput(run_id=run_id, payload={"goal": goal}, context={}),
    )
    if not planning_output.success:
        raise SystemExit(planning_output.error or "planning failed")
    return GraphBuilder().from_payload(planning_output.data["graph"])


if __name__ == "__main__":
    asyncio.run(main())
