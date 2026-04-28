"""External coding executor MVP tests."""

from __future__ import annotations

import shlex
from pathlib import Path

from app.contracts.agent import AgentTask, SharedWorkspace
from app.contracts.message import ChatMessage
from app.contracts.planner import Plan, PlanStep
from app.contracts.run import RunChoice, RunRequest, RunResult
from app.db.sqlite import SQLiteDB
from app.llm.client import LLMProvider
from app.trace.recorder import JsonlTraceRecorder
from app.trace.repository import SQLiteTraceRepository
from app.v1.tools.registry import ToolRegistry
from app.v2.agent_impls.external_coder import ExternalCodingAgent
from app.v2.base import AgentContext
from app.v2.external_command_templates import build_external_command_from_template
from app.v2.runtime import OrchestratorRuntime


class DummyProvider(LLMProvider):
    def chat(self, chat_request: RunRequest) -> RunResult:  # pragma: no cover - not used in this test
        return RunResult(
            id="dummy",
            model=chat_request.model,
            choices=[RunChoice(index=0, message=ChatMessage(role="assistant", content="ok"))],
        )


def _make_context(tmp_path: Path) -> AgentContext:
    db = SQLiteDB(tmp_path / "external-mvp.sqlite3")
    registry = ToolRegistry(workspace_root=tmp_path)
    registry.register_default_tools()
    return AgentContext(
        provider=DummyProvider(),
        model="dummy-model",
        reasoning_mode="default",
        tool_registry=registry,
        trace_repository=SQLiteTraceRepository(db),
        trace_recorder=JsonlTraceRecorder(run_id="run-1", trace_dir=tmp_path / ".traces"),
        workspace_root=tmp_path,
        session_id="s1",
        run_id="r1",
    )


def test_external_coding_agent_builds_command_from_templates(tmp_path: Path) -> None:
    agent = ExternalCodingAgent()
    context = _make_context(tmp_path)
    result = agent.run(
        task=AgentTask(
            session_id="s1",
            run_id="r1",
            step_type="coding",
            target_agent="external_coder",
            goal="执行外部编码",
            input_data={"executor": "external", "external_agent": "codex_cli"},
        ),
        workspace=SharedWorkspace(session_id="s1", run_id="r1", user_goal="修复 bug"),
        context=context,
        prompt_context={
            "orchestrator_context": {
                "policy": {
                    "external_coding": {
                        "enabled": True,
                        "preferred_agent": "codex_cli",
                        "allow_raw_external_command": False,
                        "codex_template": "pwd",
                    }
                }
            }
        },
    )
    assert result.status == "completed"
    assert result.output_data["selected_command_source"] == "template"


def test_external_coding_agent_can_execute_raw_command_when_allowed(tmp_path: Path) -> None:
    agent = ExternalCodingAgent()
    context = _make_context(tmp_path)
    result = agent.run(
        task=AgentTask(
            session_id="s1",
            run_id="r1",
            step_type="coding",
            target_agent="external_coder",
            goal="执行外部编码",
            input_data={
                "executor": "external",
                "external_agent": "codex_cli",
                "external_command": "pwd",
            },
        ),
        workspace=SharedWorkspace(session_id="s1", run_id="r1", user_goal="修复 bug"),
        context=context,
        prompt_context={
            "orchestrator_context": {
                "policy": {
                    "external_coding": {
                        "enabled": True,
                        "allow_raw_external_command": True,
                    }
                }
            }
        },
    )
    assert result.status == "completed"
    assert result.output_data["executor"] == "external"
    assert result.output_data["selected_command_source"] == "raw"


def test_external_coding_agent_reports_tool_error_detail(tmp_path: Path) -> None:
    agent = ExternalCodingAgent()
    context = _make_context(tmp_path)
    result = agent.run(
        task=AgentTask(
            session_id="s1",
            run_id="r1",
            step_type="coding",
            target_agent="external_coder",
            goal="执行外部编码",
            input_data={
                "executor": "external",
                "external_agent": "codex_cli",
                "external_command": "missing_external_coder_cli --version",
            },
        ),
        workspace=SharedWorkspace(session_id="s1", run_id="r1", user_goal="修复 bug"),
        context=context,
        prompt_context={
            "orchestrator_context": {
                "policy": {
                    "external_coding": {
                        "enabled": True,
                        "allow_raw_external_command": True,
                    }
                }
            }
        },
    )

    assert result.status == "failed"
    assert "Command is not allowed: missing_external_coder_cli" in (result.error_message or "")
    assert result.output_data["error"]


def test_template_injects_cursor_cli_path_from_policy(tmp_path: Path) -> None:
    fake_bin = tmp_path / "cursor"
    fake_bin.write_text("#!/bin/sh\necho ok\n")
    fake_bin.chmod(0o755)
    cmd = build_external_command_from_template(
        external_agent="cursor_cli",
        prompt="hi",
        workspace_root=tmp_path,
        external_policy={"cursor_cli_path": str(fake_bin)},
    )
    argv = shlex.split(cmd)
    assert argv[0] == str(fake_bin.resolve())
    assert "--trust" in argv


def test_template_adds_cursor_trust_flag_for_legacy_templates(tmp_path: Path) -> None:
    fake_bin = tmp_path / "cursor-agent"
    fake_bin.write_text("#!/bin/sh\necho ok\n")
    fake_bin.chmod(0o755)

    cmd = build_external_command_from_template(
        external_agent="cursor_cli",
        prompt="hi",
        workspace_root=tmp_path,
        template_overrides={"cursor_cli": "cursor-agent {prompt}"},
        external_policy={"cursor_cli_path": str(fake_bin)},
    )

    assert shlex.split(cmd) == [str(fake_bin.resolve()), "--trust", "hi"]


def test_template_keeps_explicit_cursor_trust_flag(tmp_path: Path) -> None:
    fake_bin = tmp_path / "cursor-agent"
    fake_bin.write_text("#!/bin/sh\necho ok\n")
    fake_bin.chmod(0o755)

    cmd = build_external_command_from_template(
        external_agent="cursor_cli",
        prompt="hi",
        workspace_root=tmp_path,
        template_overrides={"cursor_cli": "cursor-agent --yolo {prompt}"},
        external_policy={"cursor_cli_path": str(fake_bin)},
    )

    assert shlex.split(cmd) == [str(fake_bin.resolve()), "--yolo", "hi"]


def test_template_builder_rejects_unknown_agent(tmp_path: Path) -> None:
    try:
        build_external_command_from_template(
            external_agent="unknown_cli",
            prompt="fix bug",
            workspace_root=tmp_path,
        )
    except ValueError as exc:
        assert "unsupported external_agent" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for unknown external agent")


def test_runtime_routes_external_coding_step_to_external_agent(tmp_path: Path) -> None:
    db = SQLiteDB(tmp_path / "route.sqlite3")
    trace_repository = SQLiteTraceRepository(db)
    from app.v2.registry import AgentRegistry

    runtime = OrchestratorRuntime(registry=AgentRegistry(), trace_repository=trace_repository)
    step = PlanStep(
        title="复杂编码",
        goal="调用外部编码 agent",
        type="coding",
        suggested_agent="coder",
        executor="external",
    )
    assert runtime._resolve_step_target_agent(step) == "external_coder"  # type: ignore[attr-defined]


def test_runtime_reroutes_disabled_internal_coder_step_to_external_coder(tmp_path: Path) -> None:
    db = SQLiteDB(tmp_path / "route-policy.sqlite3")
    trace_repository = SQLiteTraceRepository(db)
    from app.v2.registry import AgentRegistry

    runtime = OrchestratorRuntime(registry=AgentRegistry(), trace_repository=trace_repository)
    plan = Plan(
        summary="需要外部编码",
        steps=[
            PlanStep(
                title="根据分析结果修改代码",
                goal="修复复杂 bug",
                type="coding",
                suggested_agent="coder",
            )
        ],
    )

    filtered = runtime._filter_plan_by_enabled_agents(  # type: ignore[attr-defined]
        plan=plan,
        enabled_agents={"orchestrator", "planner", "analyst", "external_coder"},
        external_coding={"enabled": True, "preferred_agent": "codex_cli"},
    )

    assert len(filtered.steps) == 1
    step = filtered.steps[0]
    assert step.suggested_agent == "external_coder"
    assert step.executor == "external"
    assert step.external_agent == "codex_cli"
    assert step.external_prompt == "修复复杂 bug"
    assert filtered.metadata["rerouted_external_coding_steps"]
