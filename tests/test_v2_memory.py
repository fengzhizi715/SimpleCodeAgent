"""Tests for V2 memory governance."""

from __future__ import annotations

from app.contracts.agent import AgentSpec, AgentTask, SharedWorkspace
from app.v2.context import ContextBuilder
from app.v2.memory import PrivateMemory, SharedMemory, V2MemoryManager, V2MemoryPolicy
from app.v2.workspace import WorkspaceStore


def test_v2_memory_manager_separates_private_context_by_agent() -> None:
    workspace = SharedWorkspace(session_id="session", run_id="run", user_goal="demo")
    workspace.private_context["analyst"] = {"project_summary": "analysis", "secret_detail": "a" * 20}
    workspace.private_context["coder"] = {"modified_files": ["app.py"]}
    manager = V2MemoryManager(policy=V2MemoryPolicy(max_string_chars=10))

    coder_context = manager.build_agent_context(agent_id="coder", workspace=workspace)
    tester_context = manager.build_agent_context(agent_id="tester", workspace=workspace)

    assert coder_context["analysis_context"]["project_summary"] == "analysis"
    assert coder_context["analysis_context"]["secret_detail"].endswith("<trimmed>")
    assert "coder_context" not in coder_context
    assert tester_context["coder_context"]["modified_files"] == ["app.py"]


def test_context_builder_uses_memory_policy_for_context_trimming() -> None:
    workspace = SharedWorkspace(session_id="session", run_id="run", user_goal="demo")
    workspace.execution_notes = ["n1", "n2", "n3"]
    workspace.project_summary = "x" * 30
    builder = ContextBuilder(
        memory_manager=V2MemoryManager(
            policy=V2MemoryPolicy(max_execution_notes=2, max_string_chars=12)
        )
    )
    task = AgentTask(
        session_id="session",
        run_id="run",
        goal="code",
        target_agent="coder",
        input_data={"large_blob": "y" * 30},
    )
    agent = AgentSpec(agent_id="coder", role="coder", description="coder")

    context = builder.build(agent=agent, task=task, workspace=workspace)

    assert context["execution_notes"] == ["n2", "n3"]
    assert str(context["project_summary"]).endswith("<trimmed>")
    assert str(context["task_input"]["large_blob"]).endswith("<trimmed>")
    assert context["memory_policy"]["max_execution_notes"] == 2
    assert context["memory_policy"]["private_sources"] == ["analyst"]


def test_workspace_store_writes_private_memory_through_abstraction() -> None:
    workspace = SharedWorkspace(session_id="session", run_id="run", user_goal="demo")
    store = WorkspaceStore(workspace)
    store.upsert_private_context("coder", {"patch_id": "p1"})

    assert PrivateMemory(workspace).read("coder") == {"patch_id": "p1"}
    assert SharedMemory(workspace).read("user_goal") == "demo"
