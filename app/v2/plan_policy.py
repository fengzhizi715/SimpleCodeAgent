"""与 Planner 解耦的「计划归一化」策略。

PlannerAgent 只负责向 LLM 要草稿步骤；本模块用可测的规则做教学友好的默认形态，
避免「未分析就测试/改代码」等明显不佳顺序，而不把业务规则写死在 prompt 里。
"""

from __future__ import annotations

import uuid

from app.contracts.planner import PlanStep, PlanStepType

# 在尚无 project_summary 时，若首步就是验证/改代码，先插入 analyst
_BUGFIX_GOAL_KEYWORDS: tuple[str, ...] = (
    "修复",
    "bug",
    "登录",
    "无法",
    "失败",
    "错误",
    "fix",
    "error",
    "login",
    "auth",
    "崩",
    "挂",
    "不工作",
    "broken",
    "fails",
    "throw",
    "异常",
    "defect",
)


def _goal_suggests_implementation_work(goal: str) -> bool:
    g = (goal or "").lower()
    return any(k in g for k in _BUGFIX_GOAL_KEYWORDS)


def _first_step_is_analysis_heavy(step: PlanStep) -> bool:
    if (step.suggested_agent or "") == "analyst":
        return True
    if step.type in ("analysis", "planning"):
        return True
    return False


def _first_step_rushes_verify_or_code(step: PlanStep) -> bool:
    agent = (step.suggested_agent or "").lower()
    stype: PlanStepType | str = step.type
    if agent in ("tester", "coder"):
        return True
    if stype in ("testing", "coding", "validation"):
        return True
    return False


def apply_step_list_policy(
    steps: list[PlanStep],
    *,
    user_goal: str,
    project_summary: str,
) -> list[PlanStep]:
    """在 _enrich_step 之前应用：需要时于队首插入「先分析」步。

    条件（同时满足才插入，避免与 LLM 已产出 analyst 首步重复）：

    1. 有步骤；
    2. 用户目标像「修问题/修登录」等需要理解仓库的任务；
    3. 当前没有可用的项目摘要（空则视为尚未分析过）；
    4. 首步是测试/编码向，而不是分析向。
    """
    if not steps:
        return steps
    if not _goal_suggests_implementation_work(user_goal):
        return steps
    if str(project_summary or "").strip():
        return steps
    if _first_step_is_analysis_heavy(steps[0]):
        return steps
    if not _first_step_rushes_verify_or_code(steps[0]):
        return steps
    primer = PlanStep(
        id=str(uuid.uuid4()),
        title="仓库结构与技术栈分析",
        goal="在改代码或跑测之前，先扫一遍仓库、识别构建/测试入口，并输出可供 Coder/Tester 使用的项目摘要。",
        type="analysis",
        description="默认前置分析（由 plan_policy 插入），与教学期望「先分析再动代码」一致。",
        suggested_agent="analyst",
        input_requirements=["用户目标", "工作区根目录"],
        success_criteria=["提供 project_summary 与可操作的 key_files 或技术栈线索"],
    )
    return [primer, *steps]
