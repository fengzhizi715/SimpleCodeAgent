"""Built-in planning skill for V3."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.contracts.message import ChatMessage
from app.contracts.run import RunRequest
from app.llm.client import LLMProvider
from app.v3.contracts.event_contracts import EventType
from app.v3.contracts.event_contracts import V3Event
from app.v3.contracts.planning_contracts import PlanningResult, RecoveryStrategy
from app.v3.skills.base import Skill
from app.v3.contracts.skill_contracts import SkillInput, SkillOutput
from app.v3.skills.builtin.project_profile import infer_goal_kind, inspect_workspace


class _LLMPlanningDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    goal_kind: str | None = None
    should_include_retrieval: bool | None = None
    recovery_strategy: RecoveryStrategy | None = None
    template_reason: str = ""
    planner_notes: list[str] = Field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class PlanningSkill(Skill):
    """Generate a repo-aware graph from a user goal."""

    def __init__(
        self,
        spec,
        *,
        provider: LLMProvider | None = None,
        model: str | None = None,
        default_planning_mode: str = "rule_based",
    ) -> None:
        super().__init__(spec)
        self.provider = provider
        self.model = model
        self.default_planning_mode = default_planning_mode

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        user_goal = str(skill_input.payload.get("goal", "")).strip()
        workspace_root = (
            skill_input.payload.get("workspace_root")
            or skill_input.context.get("workspace_root")
            or "."
        )
        rag_id = str(skill_input.payload.get("rag_id") or "").strip() or None
        rag_ids = [
            str(item).strip()
            for item in skill_input.payload.get("rag_ids", [])
            if str(item).strip()
        ]
        coding_execution_mode = str(skill_input.payload.get("coding_execution_mode") or "internal").strip().lower() or "internal"
        planning_mode = str(
            skill_input.payload.get("planning_mode")
            or self.default_planning_mode
            or "rule_based"
        ).strip().lower() or "rule_based"
        external_coding = self._build_external_coding_payload(skill_input.payload)
        profile = inspect_workspace(str(workspace_root))
        goal_kind = infer_goal_kind(user_goal)
        commands = profile.get("candidate_test_commands", [])
        candidate_test_commands = [str(command) for command in commands] if isinstance(commands, list) else []
        candidate_test_targets = [
            str(target)
            for target in profile.get("candidate_test_targets", [])
            if isinstance(target, str)
        ]
        llm_decision = await self._resolve_planning_decision(
            planning_mode=planning_mode,
            run_id=skill_input.run_id,
            user_goal=user_goal,
            profile=profile,
            goal_kind=goal_kind,
            rag_id=rag_id,
            rag_ids=rag_ids,
            coding_execution_mode=coding_execution_mode,
            context=skill_input.context,
        )
        effective_goal_kind = llm_decision.goal_kind or goal_kind
        template_name, template_reason, planner_notes, nodes = self._build_graph_template(
            user_goal=user_goal,
            goal_kind=effective_goal_kind,
            workspace_root=str(profile["workspace_root"]),
            candidate_test_commands=candidate_test_commands,
            candidate_test_targets=candidate_test_targets,
            rag_id=rag_id,
            rag_ids=rag_ids,
            coding_execution_mode=coding_execution_mode,
            external_coding=external_coding,
            force_include_retrieval=llm_decision.should_include_retrieval,
            template_reason_override=llm_decision.template_reason,
            planner_notes_prefix=llm_decision.planner_notes,
        )

        trigger_rules = self._build_trigger_templates(
            user_goal=user_goal,
            goal_kind=effective_goal_kind,
            workspace_root=str(profile["workspace_root"]),
            test_command=self._select_full_suite_command(candidate_test_commands),
            candidate_test_targets=candidate_test_targets,
            coding_execution_mode=coding_execution_mode,
            external_coding=external_coding,
        )
        recovery_strategy = (
            llm_decision.recovery_strategy
            or self._select_recovery_strategy(
                user_goal=user_goal,
                goal_kind=effective_goal_kind,
            )
        ) if trigger_rules else RecoveryStrategy.NONE
        planning_result = PlanningResult.model_validate(
            {
                "graph": {
                    "graph_id": f"graph_for_{skill_input.run_id}",
                    "run_id": skill_input.run_id,
                    "nodes": nodes,
                },
                "repo_profile": profile["repo_profile"],
                "goal_kind": effective_goal_kind,
                "recovery_strategy": recovery_strategy.value,
                "planning_mode": planning_mode,
                "coding_execution_mode": coding_execution_mode,
                "template_name": template_name,
                "template_reason": template_reason,
                "planner_notes": planner_notes,
                "rag_id": rag_id,
                "rag_ids": rag_ids,
                "candidate_test_commands": candidate_test_commands,
                "candidate_test_targets": candidate_test_targets,
                "trigger_rules": trigger_rules,
                "prompt_tokens": llm_decision.prompt_tokens,
                "completion_tokens": llm_decision.completion_tokens,
                "total_tokens": llm_decision.total_tokens,
            }
        )
        return SkillOutput(
            success=True,
            summary=(
                f"Generated {len(nodes)}-node graph for goal: "
                f"{user_goal or 'unspecified goal'}"
            ),
            data=planning_result.model_dump(mode="json"),
        )

    async def _resolve_planning_decision(
        self,
        *,
        planning_mode: str,
        run_id: str,
        user_goal: str,
        profile: dict[str, object],
        goal_kind: str,
        rag_id: str | None,
        rag_ids: list[str],
        coding_execution_mode: str,
        context: dict[str, object],
    ) -> _LLMPlanningDecision:
        if planning_mode != "llm":
            return _LLMPlanningDecision()
        if self.provider is None:
            raise ValueError("LLM planning mode requires a configured provider.")
        if not self.model:
            raise ValueError("LLM planning mode requires a resolved model.")

        prompt = (
            "You are a controlled V3 planner selector.\n"
            "Choose planning metadata only. Do not generate arbitrary graph JSON.\n"
            "Return strict JSON with fields: "
            "goal_kind, should_include_retrieval, recovery_strategy, template_reason, planner_notes.\n"
            "goal_kind must be one of analysis, coding, testing, general.\n"
            "recovery_strategy must be one of none, fix_only, fix_and_retest.\n"
            "planner_notes must be a JSON array of short strings.\n"
            "Prefer minimal safe plans."
        )
        user_message = json.dumps(
            {
                "goal": user_goal,
                "repo_profile": profile.get("repo_profile"),
                "candidate_test_commands": profile.get("candidate_test_commands", []),
                "candidate_test_targets": profile.get("candidate_test_targets", []),
                "heuristic_goal_kind": goal_kind,
                "rag_id": rag_id,
                "rag_ids": rag_ids,
                "coding_execution_mode": coding_execution_mode,
            },
            ensure_ascii=True,
        )
        await self._publish_llm_event(
            context=context,
            event=V3Event(
                run_id=run_id,
                event_type=EventType.LLM_CALLED.value,
                source=self.spec.name,
                payload={
                    "model": self.model,
                    "planning_mode": planning_mode,
                    "goal": user_goal,
                },
            ),
        )
        response = self.provider.chat(
            RunRequest(
                model=self.model,
                messages=[
                    ChatMessage(role="system", content=prompt),
                    ChatMessage(role="user", content=user_message),
                ],
            )
        )
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        if response.usage is not None:
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
            total_tokens = response.usage.total_tokens
        await self._publish_llm_event(
            context=context,
            event=V3Event(
                run_id=run_id,
                event_type=EventType.LLM_RESPONDED.value,
                source=self.spec.name,
                payload={
                    "model": self.model,
                    "planning_mode": planning_mode,
                    "choice_count": len(response.choices),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                },
            ),
        )
        content = self._extract_json_payload(response.choices[0].message.content or "")
        try:
            raw = json.loads(content)
            decision = _LLMPlanningDecision.model_validate(raw)
            decision.prompt_tokens = prompt_tokens
            decision.completion_tokens = completion_tokens
            decision.total_tokens = total_tokens
            return decision
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"LLM planning returned invalid decision payload: {exc}") from exc

    async def _publish_llm_event(self, *, context: dict[str, object], event: V3Event) -> None:
        event_bus = context.get("event_bus")
        publish = getattr(event_bus, "publish", None)
        if callable(publish):
            await publish(event)

    def _extract_json_payload(self, content: str) -> str:
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text

    def _build_trigger_templates(
        self,
        *,
        user_goal: str,
        goal_kind: str,
        workspace_root: str,
        test_command: str,
        candidate_test_targets: list[str],
        coding_execution_mode: str,
        external_coding: dict[str, object],
    ) -> list[dict[str, object]]:
        if goal_kind not in {"coding", "testing", "general"} or not test_command:
            return []

        recovery_strategy = self._select_recovery_strategy(user_goal=user_goal, goal_kind=goal_kind)
        fix_goal = (
            "A test step failed in this repository. "
            f"Fix the failing implementation with the smallest possible code change so `{test_command}` passes. "
            f"Original user goal: {user_goal or 'unspecified goal'}. "
            "Edit repository files directly and summarize the patch."
        )
        if recovery_strategy == RecoveryStrategy.FIX_AND_RETEST:
            return [
                {
                    "rule_id": "template_fix_and_retest_after_test_failed",
                    "event_type": EventType.TEST_FAILED.value,
                    "target_skill_name": "tdd",
                    "enabled": True,
                    "recovery_on_success": True,
                    "input_mapping": {
                        "goal": fix_goal,
                        "workspace_root": workspace_root,
                        "command": test_command,
                        "allow_mock_fallback": False,
                        "resume_from_failure": True,
                        "max_rounds": 2,
                        "coding_execution_mode": coding_execution_mode,
                        "success_criteria": [f"{test_command} passes"],
                        "preferred_test_targets": candidate_test_targets[:2],
                        "verify_full_suite": True,
                        **external_coding,
                    },
                }
            ]
        return [
            {
                "rule_id": "template_fix_after_test_failed",
                "event_type": EventType.TEST_FAILED.value,
                "target_skill_name": "coding",
                "enabled": True,
                "recovery_on_success": True,
                "input_mapping": {
                    "goal": fix_goal,
                    "workspace_root": workspace_root,
                    "allow_mock_fallback": False,
                    "execution_mode": coding_execution_mode,
                    "success_criteria": [f"{test_command} passes"],
                    **external_coding,
                },
            }
        ]

    def _select_recovery_strategy(self, *, user_goal: str, goal_kind: str) -> RecoveryStrategy:
        text = user_goal.lower()
        fix_only_markers = (
            "fix only",
            "only fix",
            "just fix",
            "只修复",
            "不要重跑",
            "不重跑",
        )
        if any(marker in text for marker in fix_only_markers):
            return RecoveryStrategy.FIX_ONLY

        fix_and_retest_markers = (
            "re-test",
            "retest",
            "run tests",
            "run the tests",
            "verify",
            "until pass",
            "执行测试",
            "运行测试",
            "重跑测试",
            "重新测试",
            "测试通过",
            "修到测试通过",
            "recover",
        )
        if goal_kind == "testing" or any(marker in text for marker in fix_and_retest_markers):
            return RecoveryStrategy.FIX_AND_RETEST
        return RecoveryStrategy.FIX_ONLY

    def _build_graph_template(
        self,
        *,
        user_goal: str,
        goal_kind: str,
        workspace_root: str,
        candidate_test_commands: list[str],
        candidate_test_targets: list[str],
        rag_id: str | None,
        rag_ids: list[str],
        coding_execution_mode: str,
        external_coding: dict[str, object],
        force_include_retrieval: bool | None = None,
        template_reason_override: str = "",
        planner_notes_prefix: list[str] | None = None,
    ) -> tuple[str, str, list[str], list[dict[str, object]]]:
        retrieval_required = (
            force_include_retrieval
            if force_include_retrieval is not None
            else self._should_include_retrieval(user_goal=user_goal, rag_id=rag_id, rag_ids=rag_ids)
        )
        notes_prefix = list(planner_notes_prefix or [])
        nodes: list[dict[str, object]] = []
        analyze_dependencies: list[str] = []
        if retrieval_required:
            nodes.append(
                {
                    "node_id": "retrieve_docs",
                    "skill_name": "retrieve_docs",
                    "input_payload": {
                        "goal": user_goal,
                        "query": user_goal,
                        "workspace_root": workspace_root,
                        "rag_id": rag_id,
                        "rag_ids": rag_ids,
                    },
                    "dependencies": [],
                }
            )
            analyze_dependencies.append("retrieve_docs")

        analyze_node = {
            "node_id": "analyze_repo",
            "skill_name": "analyze_repo",
            "input_payload": {
                "goal": user_goal,
                "workspace_root": workspace_root,
            },
            "dependencies": analyze_dependencies,
        }
        nodes.append(analyze_node)
        if goal_kind == "analysis":
            nodes.append(
                {
                    "node_id": "analysis_summary",
                    "skill_name": "coding",
                    "input_payload": {
                        "goal": f"Analyze and summarize the project structure based on the repository inspection. Goal: {user_goal}",
                        "workspace_root": workspace_root,
                        "execution_mode": "internal",
                    },
                    "dependencies": ["analyze_repo"],
                }
            )
            return (
                "analysis_with_context" if retrieval_required else "analysis_only",
                template_reason_override or (
                    "Goal is analysis-oriented and retrieval context was requested, so planning loads docs before repository inspection, then summarizes findings."
                    if retrieval_required
                    else "Goal is analysis-oriented, so planning inspects the repository and summarizes findings."
                ),
                [
                    *notes_prefix,
                    "Selected analysis template: retrieve context, inspect repo, then summarize with LLM.",
                    *(
                        [f"Prepended retrieve_docs because RAG context was requested for: {', '.join(rag_ids or [rag_id or 'default'])}."]
                        if retrieval_required
                        else []
                    ),
                ],
                nodes,
            )

        full_suite_command = self._select_full_suite_command(candidate_test_commands)
        focused_commands = [
            command
            for command in candidate_test_commands
            if command != full_suite_command
        ]

        if goal_kind == "testing" and focused_commands and self._should_use_branch_testing_template(user_goal):
            for index, command in enumerate(focused_commands[:2], start=1):
                nodes.append(
                    {
                        "node_id": f"test_scope_{index}",
                        "skill_name": "test_runner",
                        "input_payload": {
                            "goal": user_goal,
                            "workspace_root": workspace_root,
                            "command": command,
                        },
                        "dependencies": ["analyze_repo"],
                    }
                )
            if full_suite_command:
                nodes.append(
                    {
                        "node_id": "test_full_suite",
                        "skill_name": "test_runner",
                        "input_payload": {
                            "goal": user_goal,
                            "workspace_root": workspace_root,
                            "command": full_suite_command,
                        },
                        "dependencies": [node["node_id"] for node in nodes[1:]],
                    }
                )
            return (
                    "testing_branch_verify",
                    template_reason_override or "Goal asks for broader test verification, so the planner fans out focused test nodes before the full suite.",
                    [
                        *notes_prefix,
                        f"Detected focused test targets: {', '.join(candidate_test_targets[:2]) or 'none'}.",
                        "Selected branch verification template to expose intermediate failures before the full suite.",
                    ],
                nodes,
            )

        if goal_kind in {"coding", "general"}:
            nodes.append(
                {
                    "node_id": "coding",
                    "skill_name": "coding",
                    "input_payload": {
                        "goal": user_goal,
                        "workspace_root": workspace_root,
                        "execution_mode": coding_execution_mode,
                        **external_coding,
                    },
                    "dependencies": ["analyze_repo"],
                }
            )

        dependency = "coding" if goal_kind in {"coding", "general"} else "analyze_repo"
        if (
            goal_kind in {"coding", "general"}
            and focused_commands
            and self._should_use_scoped_verification_template(user_goal)
        ):
            focused_command = focused_commands[0]
            nodes.append(
                {
                    "node_id": "test_changed_scope",
                    "skill_name": "test_runner",
                    "input_payload": {
                        "goal": user_goal,
                        "workspace_root": workspace_root,
                        "command": focused_command,
                    },
                    "dependencies": [dependency],
                }
            )
            if full_suite_command:
                nodes.append(
                    {
                        "node_id": "test_full_suite",
                        "skill_name": "test_runner",
                        "input_payload": {
                            "goal": user_goal,
                            "workspace_root": workspace_root,
                            "command": full_suite_command,
                        },
                        "dependencies": ["test_changed_scope"],
                    }
                )
                return (
                    "coding_focus_then_full_suite",
                    template_reason_override or "Goal asks for scoped verification, so the planner runs a focused test before the full suite.",
                    [
                        *notes_prefix,
                        f"Focused verification command: {focused_command}.",
                        f"Full-suite verification command: {full_suite_command}.",
                    ],
                    nodes,
                )

        if goal_kind in {"coding", "testing", "general"} and full_suite_command:
            nodes.append(
                {
                    "node_id": "test_runner",
                    "skill_name": "test_runner",
                    "input_payload": {
                        "goal": user_goal,
                        "workspace_root": workspace_root,
                        "command": full_suite_command,
                    },
                    "dependencies": [dependency],
                }
            )
        return (
            "default",
            template_reason_override or "Planner selected the default linear graph because no richer template was strongly indicated by the goal.",
            [
                *notes_prefix,
                f"Goal kind inferred as {goal_kind}.",
                f"Primary verification command: {full_suite_command or 'none'}.",
                f"Coding execution mode: {coding_execution_mode}.",
                *(
                    [f"Prepended retrieve_docs for RAG context: {', '.join(rag_ids or [rag_id or 'default'])}."]
                    if retrieval_required
                    else []
                ),
            ],
            nodes,
        )

    def _select_full_suite_command(self, candidate_test_commands: list[str]) -> str:
        if not candidate_test_commands:
            return ""
        for command in reversed(candidate_test_commands):
            if command.strip() == "pytest -q" or command.endswith(" test"):
                return command
        return candidate_test_commands[-1]

    def _should_use_branch_testing_template(self, user_goal: str) -> bool:
        text = user_goal.lower()
        return any(
            marker in text
            for marker in (
                "full sweep",
                "all tests",
                "分支",
                "分层测试",
                "多测试节点",
                "branch",
            )
        )

    def _should_use_scoped_verification_template(self, user_goal: str) -> bool:
        text = user_goal.lower()
        return any(
            marker in text
            for marker in (
                "scoped",
                "limited scope",
                "focus test",
                "限定范围",
                "小范围验证",
                "先跑相关测试",
            )
        )

    def _should_include_retrieval(self, *, user_goal: str, rag_id: str | None, rag_ids: list[str]) -> bool:
        if rag_id or rag_ids:
            return True
        text = user_goal.lower()
        return any(
            marker in text
            for marker in (
                "rag",
                "docs",
                "document",
                "knowledge base",
                "知识库",
                "文档",
                "检索",
            )
        )

    def _build_external_coding_payload(self, payload: dict[str, object]) -> dict[str, object]:
        preferred_agent = str(payload.get("preferred_agent") or "").strip()
        external_payload: dict[str, object] = {}
        for key in (
            "external_agent",
            "preferred_agent",
            "allow_raw_external_command",
            "external_command",
            "external_timeout_seconds",
            "codex_template",
            "cursor_template",
            "cursor_cli_path",
            "codex_cli_path",
        ):
            value = payload.get(key)
            if value not in (None, "", []):
                external_payload[key] = value
        if preferred_agent and "external_agent" not in external_payload:
            external_payload["external_agent"] = preferred_agent
        return external_payload
