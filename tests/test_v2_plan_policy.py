"""V2 plan_policy 归一化。"""

from __future__ import annotations

from app.contracts.planner import PlanStep
from app.v2.plan_policy import apply_step_list_policy


def test_prepends_analyst_when_bugfix_and_empty_summary_and_first_is_tester() -> None:
    steps = [
        PlanStep(
            title="复现",
            goal="跑测",
            type="testing",
            suggested_agent="tester",
        )
    ]
    out = apply_step_list_policy(
        steps,
        user_goal="修复无法登录的 bug",
        project_summary="",
    )
    assert len(out) == 2
    assert out[0].suggested_agent == "analyst"
    assert out[0].type == "analysis"
    assert out[1].suggested_agent == "tester"


def test_no_prepend_when_summary_exists() -> None:
    steps = [PlanStep(title="t", goal="g", type="testing", suggested_agent="tester")]
    out = apply_step_list_policy(
        steps,
        user_goal="修复登录",
        project_summary="已有分析摘要。",
    )
    assert out == steps


def test_no_prepend_when_first_already_analyst() -> None:
    steps = [PlanStep(title="看仓库", goal="g", type="analysis", suggested_agent="analyst")]
    out = apply_step_list_policy(
        steps,
        user_goal="修 bug",
        project_summary="",
    )
    assert out == steps
