"""Reviewer agent implementation."""

from __future__ import annotations

import json
import re
from typing import Literal

from app.contracts.agent import (
    AgentArtifact,
    AgentResult,
    AgentSpec,
    AgentTask,
    ReviewIssue,
    SharedWorkspace,
)
from app.contracts.run import RunMetrics, RunUsage
from app.v2.agent_impls.llm_utils import chat_json, parse_tool_content
from app.v2.agent_impls.payloads import ReviewOutputPayload
from app.v2.base import AgentBase, AgentContext

DEFAULT_RULE_GROUPS = ("scope", "testing", "security", "maintainability", "boundaries", "api", "domain")
TEST_FAILURE_MODES = {"off", "suggest", "block"}


class ReviewerAgent(AgentBase):
    """Review patch summary using rules plus optional LLM review.

    输入契约：
    - workspace.latest_patch_summary：本轮待评审改动摘要。
    - prompt_context.coder_context：modified_files / diff_previews / risk_notes。
    - prompt_context.analysis_context：关键文件信息，辅助边界检查。

    输出契约：
    - AgentResult.status：completed。
    - output_data.review_summary / issues / recommended_action。
    - artifacts：review_report 工件。
    """

    def __init__(self) -> None:
        super().__init__(
            AgentSpec(
                agent_id="reviewer",
                role="reviewer",
                description="Review patch summary and identify maintainability or correctness risks.",
                capabilities=["review", "risk-analysis", "maintainability-check"],
            )
        )

    def run(
        self,
        *,
        task: AgentTask,
        workspace: SharedWorkspace,
        context: AgentContext,
        prompt_context: dict[str, object],
    ) -> AgentResult:
        coder_context = prompt_context.get("coder_context")
        analysis_context = prompt_context.get("analysis_context")
        review_strategy = self._resolve_review_strategy(task=task, prompt_context=prompt_context)
        latest_test_result = self._coerce_mapping(prompt_context.get("latest_test_result"))
        review_materials, tool_call_count = self._collect_review_materials(
            context=context,
            coder_context=coder_context if isinstance(coder_context, dict) else {},
            analysis_context=analysis_context if isinstance(analysis_context, dict) else {},
            task=task,
        )
        rule_issues = self._build_review_issues(
            summary=workspace.latest_patch_summary,
            coder_context=coder_context if isinstance(coder_context, dict) else {},
            review_materials=review_materials,
            latest_test_result=latest_test_result,
            review_strategy=review_strategy,
        )
        llm_review, usage = self._build_llm_review(
            summary=workspace.latest_patch_summary,
            coder_context=coder_context if isinstance(coder_context, dict) else {},
            analysis_context=analysis_context,
            project_summary=str(prompt_context.get("project_summary") or workspace.project_summary),
            review_materials=review_materials,
            latest_test_result=latest_test_result,
            review_strategy=review_strategy,
            context=context,
        )
        review_issues = self._merge_review_issues(rule_issues=rule_issues, llm_review=llm_review)
        summary = self._build_review_summary(review_issues=review_issues, llm_review=llm_review)
        output_data = {
            "review_summary": summary,
            "issues": [issue.model_dump() for issue in review_issues],
            "diff_previews": review_materials["diff_previews"],
            "changed_file_snippets": review_materials["changed_file_snippets"],
            "key_file_snippets": review_materials["key_file_snippets"],
            "recommended_action": self._build_recommended_action(
                review_issues=review_issues,
                llm_review=llm_review,
            ),
            "rule_issue_count": len(rule_issues),
            "rule_group_counts": self._count_rule_groups(review_issues),
            "llm_review_used": llm_review is not None,
            "review_strategy": review_strategy,
        }
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.spec.agent_id,
            status="completed",
            summary=summary,
            usage=usage,
            metrics=RunMetrics(
                llm_call_count=1 if usage is not None else 0,
                tool_call_count=tool_call_count,
            ),
            output_data=output_data,
            artifacts=[
                AgentArtifact(
                    key="review_report",
                    type="review",
                    summary=summary,
                    producer_agent=self.spec.agent_id,
                    content=output_data,
                )
            ],
        )

    def _build_review_issues(
        self,
        *,
        summary: str,
        coder_context: dict[str, object],
        review_materials: dict[str, dict[str, str]],
        latest_test_result: dict[str, object],
        review_strategy: dict[str, object],
    ) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        modified_files = [str(item) for item in coder_context.get("modified_files", []) if str(item).strip()]
        created_files = [str(item) for item in coder_context.get("created_files", []) if str(item).strip()]
        deleted_files = [str(item) for item in coder_context.get("deleted_files", []) if str(item).strip()]
        risk_notes = [str(item) for item in coder_context.get("risk_notes", []) if str(item).strip()]
        diff_previews = review_materials.get("diff_previews", {})
        changed_file_snippets = review_materials.get("changed_file_snippets", {})
        key_file_snippets = review_materials.get("key_file_snippets", {})
        strictness = str(review_strategy.get("strictness") or "normal")
        missing_test_severity: Literal["medium", "high"] = "high" if strictness == "strict" else "medium"
        if self._rule_enabled(review_strategy, "scope") and not modified_files and not created_files and not deleted_files:
            issues.append(
                ReviewIssue(
                    severity="medium",
                    title="未检测到实际文件改动",
                    detail="Coder 输出了摘要，但没有检测到文件变化，建议确认是否真的完成修改。",
                    category="scope",
                )
            )
        if self._rule_enabled(review_strategy, "scope") and deleted_files:
            issues.append(
                ReviewIssue(
                    severity="high",
                    title="存在文件删除",
                    detail="本次修改包含文件删除，请确认不会破坏现有行为或教学路径。",
                    file_path=deleted_files[0],
                    category="scope",
                )
            )
        if self._rule_enabled(review_strategy, "scope") and len(modified_files) + len(created_files) > 6:
            issues.append(
                ReviewIssue(
                    severity="medium",
                    title="改动范围偏大",
                    detail="当前改动涉及文件较多，建议检查是否偏离了“局部修改”的目标。",
                    category="scope",
                )
            )
        if self._rule_enabled(review_strategy, "scope") and any("未检测到工作区文件变化" in note for note in risk_notes):
            issues.append(
                ReviewIssue(
                    severity="medium",
                    title="修改未落盘风险",
                    detail="存在仅生成建议未真正写入文件的风险，建议在测试前再次确认。",
                    category="scope",
                )
            )
        if self._rule_enabled(review_strategy, "maintainability") and summary and "风险" in summary and not issues:
            issues.append(
                ReviewIssue(
                    severity="low",
                    title="需人工复核",
                    detail="Coder 摘要中提到了风险，建议在继续前做人工确认。",
                    category="maintainability",
                )
            )
        if self._rule_enabled(review_strategy, "boundaries") and any(path.startswith("app/contracts/") for path in modified_files):
            issues.append(
                ReviewIssue(
                    severity="medium",
                    title="修改了共享协议层",
                    detail="本次改动涉及共享 contract，建议额外检查是否会影响 v1/v2 的边界稳定性。",
                    file_path=next(path for path in modified_files if path.startswith("app/contracts/")),
                    category="boundaries",
                )
            )
        if self._rule_enabled(review_strategy, "boundaries") and any(
            path.startswith("app/v1/") for path in modified_files + created_files + deleted_files
        ):
            issues.append(
                ReviewIssue(
                    severity="high",
                    title="触及 v1 代码路径",
                    detail="当前任务处于 v2 演进阶段，但改动触及了 v1 目录，建议重点确认没有破坏 v1 稳定性。",
                    file_path=next(
                        path
                        for path in modified_files + created_files + deleted_files
                        if path.startswith("app/v1/")
                    ),
                    category="boundaries",
                )
            )
        if self._rule_enabled(review_strategy, "testing") and not any(
            path.startswith("tests/") for path in modified_files + created_files
        ) and (
            modified_files or created_files or deleted_files
        ):
            issues.append(
                ReviewIssue(
                    severity=missing_test_severity,
                    title="缺少测试改动",
                    detail="当前代码发生了实际修改，但未检测到测试文件变更，建议确认是否已有足够覆盖。",
                    category="testing",
                )
            )
        if self._rule_enabled(review_strategy, "testing"):
            test_issue = self._build_test_feedback_issue(
                summary=summary,
                latest_test_result=latest_test_result,
                mode=str(review_strategy.get("test_failure_mode") or "block"),
            )
            if test_issue is not None:
                issues.append(test_issue)
        for path, preview in diff_previews.items():
            if not preview.strip():
                continue
            lowered = preview.lower()
            if self._rule_enabled(review_strategy, "security"):
                issues.extend(self._build_security_rule_issues(path=path, text=preview))
            if self._rule_enabled(review_strategy, "maintainability") and (
                "except Exception" in preview or "except:" in lowered
            ):
                issues.append(
                    ReviewIssue(
                        severity="medium",
                        title="存在宽泛异常捕获",
                        detail="diff 中出现了宽泛异常捕获，建议确认是否会掩盖真实错误。",
                        file_path=path,
                        category="maintainability",
                    )
                )
            if self._rule_enabled(review_strategy, "maintainability") and ("TODO" in preview or "FIXME" in preview):
                issues.append(
                    ReviewIssue(
                        severity="low",
                        title="遗留 TODO/FIXME",
                        detail="本次改动中包含 TODO/FIXME 标记，建议确认是否适合作为当前阶段提交内容。",
                        file_path=path,
                        category="maintainability",
                    )
                )
            if self._rule_enabled(review_strategy, "api") and self._looks_like_public_api_change(path=path, text=preview):
                issues.append(
                    ReviewIssue(
                        severity="medium",
                        title="公共接口变更需复核",
                        detail="diff 显示公共函数/类签名发生变化，建议确认调用方和文档是否同步更新。",
                        file_path=path,
                        category="api",
                    )
                )
        if self._rule_enabled(review_strategy, "security"):
            for path, snippet in changed_file_snippets.items():
                issues.extend(self._build_security_rule_issues(path=path, text=snippet))
        if self._rule_enabled(review_strategy, "domain") and self._touches_auth_or_storage(
            paths=modified_files + created_files + deleted_files,
            summary=summary,
            snippets={**changed_file_snippets, **key_file_snippets},
        ) and not any(path.startswith("tests/") for path in modified_files + created_files):
            issues.append(
                ReviewIssue(
                    severity="high" if strictness == "strict" else "medium",
                    title="认证或存储改动缺少测试覆盖",
                    detail="本次改动看起来触及认证、用户数据或持久化路径，但未检测到测试文件变更，建议补充回归验证。",
                    category="domain",
                )
            )
        return issues

    def _build_llm_review(
        self,
        *,
        summary: str,
        coder_context: dict[str, object],
        analysis_context: object,
        project_summary: str,
        review_materials: dict[str, dict[str, str]],
        latest_test_result: dict[str, object],
        review_strategy: dict[str, object],
        context: AgentContext,
    ) -> tuple[ReviewOutputPayload | None, RunUsage | None]:
        if not bool(review_strategy.get("llm_enabled", True)):
            return None, None
        max_issues = int(review_strategy.get("max_issues") or 5)
        focus_areas = review_strategy.get("focus_areas") or []
        system_prompt = (
            "You are the Reviewer Agent for SimpleCodeAgent V2. "
            "Return only valid JSON with keys review_summary, issues, recommended_action. "
            "issues must be a list of objects with severity, title, detail, file_path. "
            "Focus on correctness risk, test-result consistency, maintainability, boundary violations, "
            "security-sensitive changes, and missing validation. "
            "Respect enabled rule groups and review strategy. "
            "Do not restate the input unless it is relevant to a review concern."
        )
        user_prompt = "\n".join(
            [
                f"项目摘要：{project_summary}",
                f"代码改动摘要：{summary}",
                f"Coder 上下文：{json.dumps(coder_context, ensure_ascii=False)}",
                f"Analyst 上下文：{json.dumps(analysis_context, ensure_ascii=False)}",
                f"最近测试结果：{json.dumps(latest_test_result, ensure_ascii=False)}",
                f"Review 策略：{json.dumps(review_strategy, ensure_ascii=False)}",
                f"Diff 预览：{json.dumps(review_materials.get('diff_previews', {}), ensure_ascii=False)}",
                f"改动文件片段：{json.dumps(review_materials.get('changed_file_snippets', {}), ensure_ascii=False)}",
                f"关键文件片段：{json.dumps(review_materials.get('key_file_snippets', {}), ensure_ascii=False)}",
                f"请做一次简洁但严格的 code review，指出 0-{max_issues} 个最重要的问题。",
                f"优先关注：{', '.join(str(item) for item in focus_areas) if focus_areas else '默认工程风险'}。",
            ]
        )
        payload, llm_result = chat_json(context=context, system_prompt=system_prompt, user_prompt=user_prompt)
        if payload is None:
            return None, llm_result.usage if llm_result is not None else None
        try:
            return ReviewOutputPayload.model_validate(payload), llm_result.usage if llm_result is not None else None
        except Exception:
            return None, llm_result.usage if llm_result is not None else None

    def _merge_review_issues(
        self,
        *,
        rule_issues: list[ReviewIssue],
        llm_review: ReviewOutputPayload | None,
    ) -> list[ReviewIssue]:
        merged: dict[tuple[str, str | None], ReviewIssue] = {
            (issue.title, issue.file_path): issue for issue in rule_issues
        }
        if llm_review is None:
            return list(merged.values())
        severity_rank = {"low": 1, "medium": 2, "high": 3}
        for item in llm_review.issues:
            key = (item.title, item.file_path)
            candidate = ReviewIssue(
                severity=item.severity,
                title=item.title,
                detail=item.detail,
                file_path=item.file_path,
            )
            existing = merged.get(key)
            if existing is None:
                merged[key] = candidate
                continue
            if candidate.category is None and existing.category is not None:
                candidate.category = existing.category
            if severity_rank[candidate.severity] > severity_rank[existing.severity]:
                merged[key] = candidate
            elif len(candidate.detail) > len(existing.detail):
                merged[key] = candidate
        return sorted(
            merged.values(),
            key=lambda issue: (
                {"high": 0, "medium": 1, "low": 2}[issue.severity],
                issue.title,
            ),
        )

    def _build_review_summary(
        self,
        *,
        review_issues: list[ReviewIssue],
        llm_review: ReviewOutputPayload | None,
    ) -> str:
        if llm_review is not None and llm_review.review_summary.strip():
            if review_issues:
                return llm_review.review_summary.strip()
            return llm_review.review_summary.strip() or "Review 未发现明显阻塞问题。"
        if not review_issues:
            return "Review 未发现明显阻塞问题。"
        high_count = sum(issue.severity == "high" for issue in review_issues)
        medium_count = sum(issue.severity == "medium" for issue in review_issues)
        return f"Review 发现 {len(review_issues)} 个需要关注的问题，其中高风险 {high_count} 个、中风险 {medium_count} 个。"

    def _build_recommended_action(
        self,
        *,
        review_issues: list[ReviewIssue],
        llm_review: ReviewOutputPayload | None,
    ) -> str:
        if llm_review is not None and llm_review.recommended_action.strip():
            return llm_review.recommended_action.strip()
        if any(issue.severity == "high" for issue in review_issues):
            return "建议先处理高风险 review 问题，再进入测试验证。"
        if any(issue.severity == "medium" for issue in review_issues):
            return "建议优先处理中风险 review 问题，再继续后续验证。"
        return "可以继续进入测试验证。"

    def _resolve_review_strategy(self, *, task: AgentTask, prompt_context: dict[str, object]) -> dict[str, object]:
        raw = {}
        prompt_strategy = prompt_context.get("review_strategy")
        if isinstance(prompt_strategy, dict):
            raw.update(prompt_strategy)
        task_strategy = task.input_data.get("review_strategy") if isinstance(task.input_data, dict) else None
        if isinstance(task_strategy, dict):
            raw.update(task_strategy)
        strictness = str(raw.get("strictness") or "normal").lower()
        if strictness not in {"light", "normal", "strict"}:
            strictness = "normal"
        max_issues = raw.get("max_issues", 5)
        try:
            max_issues_int = int(max_issues)
        except (TypeError, ValueError):
            max_issues_int = 5
        max_issues_int = min(max(max_issues_int, 1), 10)
        focus_areas = raw.get("focus_areas", [])
        if not isinstance(focus_areas, list):
            focus_areas = []
        return {
            "llm_enabled": bool(raw.get("llm_enabled", True)),
            "strictness": strictness,
            "max_issues": max_issues_int,
            "focus_areas": [str(item) for item in focus_areas if str(item).strip()][:8],
            "rule_groups": self._normalize_rule_groups(raw.get("rule_groups")),
            "test_failure_mode": self._normalize_test_failure_mode(raw.get("test_failure_mode")),
        }

    def _coerce_mapping(self, value: object) -> dict[str, object]:
        return value if isinstance(value, dict) else {}

    def _build_test_feedback_issue(
        self,
        *,
        summary: str,
        latest_test_result: dict[str, object],
        mode: str,
    ) -> ReviewIssue | None:
        if mode == "off":
            return None
        if not latest_test_result:
            lowered_summary = summary.lower()
            if any(token in lowered_summary for token in ("测试通过", "编译成功", "build successful", "passed")):
                return ReviewIssue(
                    severity="low",
                    title="验证结论缺少结构化测试记录",
                    detail="Coder 摘要声称已验证通过，但 Reviewer 未收到 latest_test_result，建议确认验证结果是否已进入 trace/workspace。",
                    category="testing",
                )
            return None
        status = str(latest_test_result.get("status") or "").lower()
        executed_command = str(latest_test_result.get("executed_command") or "")
        test_summary = str(latest_test_result.get("summary") or "")
        failure_type = str(latest_test_result.get("failure_type") or "")
        if status == "passed":
            return None
        if failure_type in {"command_blocked", "no_tests_collected"}:
            return ReviewIssue(
                severity="medium",
                title="验证未形成有效结论",
                detail=f"最近验证未能形成有效测试结论（{executed_command}）：{test_summary}",
                category="testing",
            )
        return ReviewIssue(
            severity="high" if mode == "block" else "medium",
            title="测试失败仍未解决",
            detail=f"最近验证失败（{executed_command}）：{test_summary}。Reviewer 不应放行该改动。",
            category="testing",
        )

    def _build_security_rule_issues(self, *, path: str, text: str) -> list[ReviewIssue]:
        lowered = text.lower()
        issues: list[ReviewIssue] = []
        security_patterns: list[tuple[str, str, str]] = [
            ("危险动态执行", r"\b(eval|exec)\s*\(", "diff 中出现 eval/exec，建议确认是否存在代码注入风险。"),
            ("不安全反序列化", r"\bpickle\.loads?\s*\(", "diff 中出现 pickle 反序列化，建议确认输入是否完全可信。"),
            ("不安全 YAML 加载", r"yaml\.load\s*\(", "diff 中出现 yaml.load，建议使用 safe_load 或显式 Loader。"),
            ("Shell 注入风险", r"shell\s*=\s*True|os\.system\s*\(|subprocess\.(run|popen|call)\s*\(", "diff 中出现 shell/subprocess 调用，建议确认参数来源和转义策略。"),
            ("疑似硬编码密钥", r"(api[_-]?key|secret|token|password)\s*=\s*['\"][^'\"]{8,}", "diff 中疑似出现硬编码密钥或密码。"),
        ]
        for title, pattern, detail in security_patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                issues.append(ReviewIssue(severity="high", title=title, detail=detail, file_path=path, category="security"))
        if "../" in text or "..\\" in text:
            issues.append(
                ReviewIssue(
                    severity="medium",
                    title="路径穿越风险",
                    detail="diff 中出现上级目录路径片段，建议确认文件路径已限制在工作区内。",
                    file_path=path,
                    category="security",
                )
            )
        if "chmod 777" in lowered:
            issues.append(
                ReviewIssue(
                    severity="medium",
                    title="文件权限过宽",
                    detail="diff 中出现 chmod 777，建议使用更小权限范围。",
                    file_path=path,
                    category="security",
                )
            )
        return issues

    def _normalize_rule_groups(self, raw_groups: object) -> list[str]:
        if not isinstance(raw_groups, list):
            return list(DEFAULT_RULE_GROUPS)
        selected = [str(item).strip().lower() for item in raw_groups if str(item).strip()]
        return [group for group in DEFAULT_RULE_GROUPS if group in selected]

    def _normalize_test_failure_mode(self, raw_mode: object) -> str:
        mode = str(raw_mode or "block").strip().lower()
        return mode if mode in TEST_FAILURE_MODES else "block"

    def _rule_enabled(self, review_strategy: dict[str, object], group: str) -> bool:
        raw_groups = review_strategy.get("rule_groups")
        if not isinstance(raw_groups, list):
            return True
        return group in {str(item) for item in raw_groups}

    def _count_rule_groups(self, issues: list[ReviewIssue]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for issue in issues:
            category = issue.category or "uncategorized"
            counts[category] = counts.get(category, 0) + 1
        return counts

    def _looks_like_public_api_change(self, *, path: str, text: str) -> bool:
        if path.startswith("tests/"):
            return False
        return bool(re.search(r"^[+-]\s*(def|class|export\s+function|public\s+|fun\s+)\s+\w+", text, re.MULTILINE))

    def _touches_auth_or_storage(
        self,
        *,
        paths: list[str],
        summary: str,
        snippets: dict[str, str],
    ) -> bool:
        haystack = " ".join([summary, *paths, *snippets.values()]).lower()
        return any(
            token in haystack
            for token in (
                "auth",
                "login",
                "password",
                "token",
                "userrepository",
                "storage",
                "database",
                "sqlite",
                "persist",
                "认证",
                "登录",
                "密码",
                "存储",
                "数据库",
            )
        )

    def _collect_review_materials(
        self,
        *,
        context: AgentContext,
        coder_context: dict[str, object],
        analysis_context: dict[str, object],
        task: AgentTask,
    ) -> tuple[dict[str, dict[str, str]], int]:
        diff_previews = {
            str(path): str(preview)
            for path, preview in (coder_context.get("diff_previews", {}) or {}).items()
            if str(path).strip() and str(preview).strip()
        }
        changed_files = []
        for key in ("modified_files", "created_files"):
            values = coder_context.get(key, [])
            if isinstance(values, list):
                changed_files.extend(str(value) for value in values if str(value).strip())
        changed_file_snippets, changed_read_count = self._read_file_snippets(
            context=context,
            paths=changed_files[:4],
            task=task,
            prefix="review-changed",
        )
        key_files: list[str] = []
        raw_key_files = analysis_context.get("key_files", [])
        if isinstance(raw_key_files, list):
            for item in raw_key_files[:4]:
                if isinstance(item, dict) and item.get("path"):
                    key_files.append(str(item["path"]))
                elif isinstance(item, str):
                    key_files.append(item)
        key_file_snippets, key_read_count = self._read_file_snippets(
            context=context,
            paths=key_files,
            task=task,
            prefix="review-key",
        )
        return (
            {
                "diff_previews": diff_previews,
                "changed_file_snippets": changed_file_snippets,
                "key_file_snippets": key_file_snippets,
            },
            changed_read_count + key_read_count,
        )

    def _read_file_snippets(
        self,
        *,
        context: AgentContext,
        paths: list[str],
        task: AgentTask,
        prefix: str,
    ) -> tuple[dict[str, str], int]:
        snippets: dict[str, str] = {}
        read_call_count = 0
        for index, path in enumerate(paths, start=1):
            result = context.tool_registry.execute_tool(
                tool_name="read_file",
                arguments={"path": path, "max_chars": 1200},
                tool_call_id=f"{task.task_id}-{prefix}-{index}",
            )
            read_call_count += 1
            payload = parse_tool_content(result.content)
            content = str(payload.get("content") or "").strip()
            if content:
                snippets[path] = content
        return snippets, read_call_count
