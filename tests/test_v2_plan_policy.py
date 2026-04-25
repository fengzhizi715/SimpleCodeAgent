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
    assert [step.suggested_agent for step in out] == ["analyst", "coder", "tester"]
    assert [step.type for step in out] == ["analysis", "coding", "testing"]
    assert out[0].strategy_explanation
    assert "编码前" in out[0].strategy_explanation


def test_no_prepend_when_summary_exists() -> None:
    steps = [PlanStep(title="t", goal="g", type="testing", suggested_agent="tester")]
    out = apply_step_list_policy(
        steps,
        user_goal="修复登录",
        project_summary="已有分析摘要。",
    )
    assert [step.suggested_agent for step in out] == ["coder", "tester"]


def test_no_prepend_when_first_already_analyst() -> None:
    steps = [PlanStep(title="看仓库", goal="g", type="analysis", suggested_agent="analyst")]
    out = apply_step_list_policy(
        steps,
        user_goal="修 bug",
        project_summary="",
    )
    assert [step.suggested_agent for step in out] == ["analyst", "coder", "tester"]


def test_moves_validation_after_coder_for_bugfix_workflow() -> None:
    steps = [
        PlanStep(title="先验证", goal="运行验证命令", type="testing", suggested_agent="tester"),
        PlanStep(title="再修复", goal="修改登录逻辑", type="coding", suggested_agent="coder"),
    ]
    out = apply_step_list_policy(
        steps,
        user_goal="修复无法登录的 bug",
        project_summary="已有分析摘要。",
    )
    assert [step.suggested_agent for step in out] == ["coder", "tester"]


def test_rag_answer_generation_uses_retrieval_then_coder_only() -> None:
    steps = [
        PlanStep(title="理解任务", goal="提取任务目标", type="general", suggested_agent="coder"),
        PlanStep(title="总结结果", goal="整理最终结论", type="analysis", suggested_agent="analyst"),
    ]

    out = apply_step_list_policy(
        steps,
        user_goal="先检索相关文档根据知识库内容，写一个 OpenCV C++ 直方图匹配的算法。",
        project_summary="",
    )

    assert [step.suggested_agent for step in out] == ["analyst", "coder"]
    assert [step.tool_name for step in out] == ["retrieve_docs", None]
    assert out[0].type == "analysis"
    assert out[1].type == "coding"
    assert "docs_context" in out[1].input_requirements
    assert "不是项目结构分析" in out[1].strategy_explanation


def test_rag_answer_generation_skips_shortcut_for_repo_modification_goal() -> None:
    steps = [PlanStep(title="先分析", goal="分析仓库", type="analysis", suggested_agent="analyst")]

    out = apply_step_list_policy(
        steps,
        user_goal="先检索相关文档根据知识库内容，写一个 OpenCV 算法，并修改仓库里的文件提交 patch。",
        project_summary="",
    )

    assert [step.suggested_agent for step in out] != ["analyst", "coder"]
    assert not (len(out) == 2 and out[0].tool_name == "retrieve_docs")
