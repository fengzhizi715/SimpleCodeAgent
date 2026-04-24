"""与 Planner 解耦的「计划归一化」策略。

PlannerAgent 只负责向 LLM 要草稿步骤；本模块用可测的规则做教学友好的默认形态，
避免「未分析就测试/改代码」等明显不佳顺序，而不把业务规则写死在 prompt 里。
"""

from __future__ import annotations

import uuid

from app.contracts.planner import PlanStep, PlanStepType

# 需要改动代码的目标，应默认先识别项目，再修改，再验证。
_BUGFIX_GOAL_KEYWORDS: tuple[str, ...] = (
    "实现",
    "增加",
    "新增",
    "修改",
    "改动",
    "优化",
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
    "implement",
    "add",
    "change",
    "update",
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


def _make_default_analyst_step() -> PlanStep:
    return PlanStep(
        id=str(uuid.uuid4()),
        title="仓库结构与技术栈分析",
        goal="在改代码或跑测之前，先扫一遍仓库、识别构建/测试入口，并输出可供 Coder/Tester 使用的项目摘要。",
        type="analysis",
        description="默认前置分析（由 plan_policy 插入），与教学期望「先分析再动代码」一致。",
        suggested_agent="analyst",
        input_requirements=["用户目标", "工作区根目录"],
        success_criteria=["提供 project_summary 与可操作的 key_files 或技术栈线索"],
    )


def _make_default_coder_step(user_goal: str) -> PlanStep:
    return PlanStep(
        id=str(uuid.uuid4()),
        title="根据分析结果修改代码",
        goal=f"基于 Analyst 的项目摘要和关键文件线索，完成用户目标：{user_goal}",
        type="coding",
        description="默认编码步骤（由 plan_policy 插入），确保修复/实现类任务不会停留在分析或验证阶段。",
        suggested_agent="coder",
        input_requirements=["用户目标", "project_summary", "key_files", "latest_test_result（如有）"],
        success_criteria=["产生局部代码改动", "输出修改文件列表与变更摘要"],
    )


def _make_default_tester_step() -> PlanStep:
    return PlanStep(
        id=str(uuid.uuid4()),
        title="验证修改结果",
        goal="根据项目类型与 Coder 变更，选择合适命令进行编译或测试验证。",
        type="testing",
        description="默认验证步骤（由 plan_policy 插入），避免代码改动后缺少闭环校验。",
        suggested_agent="tester",
        input_requirements=["latest_patch_summary", "modified_files", "project_summary"],
        success_criteria=["给出结构化测试/编译报告", "明确是否通过以及下一步建议"],
    )


def _first_index_for_agent(steps: list[PlanStep], agent_id: str) -> int | None:
    for index, step in enumerate(steps):
        if (step.suggested_agent or "").lower() == agent_id:
            return index
    return None


def _insert_after_leading_analysis(steps: list[PlanStep], step: PlanStep) -> None:
    index = 0
    while index < len(steps) and _first_step_is_analysis_heavy(steps[index]):
        index += 1
    steps.insert(index, step)


def apply_step_list_policy(
    steps: list[PlanStep],
    *,
    user_goal: str,
    project_summary: str,
) -> list[PlanStep]:
    """在 _enrich_step 之前应用：归一化教学友好的默认执行顺序。

    对修复/实现类任务，默认收敛到：
    analyst（识别项目与关键文件） -> coder（局部修改） -> tester（验证）。
    """
    if not steps:
        return steps
    if not _goal_suggests_implementation_work(user_goal):
        return steps
    normalized = list(steps)
    if str(project_summary or "").strip():
        needs_initial_analysis = False
    else:
        needs_initial_analysis = (
            not _first_step_is_analysis_heavy(normalized[0])
            or _first_step_rushes_verify_or_code(normalized[0])
        )
    if needs_initial_analysis:
        normalized.insert(0, _make_default_analyst_step())

    first_coder = _first_index_for_agent(normalized, "coder")
    first_tester = _first_index_for_agent(normalized, "tester")
    if first_coder is None:
        coder_step = _make_default_coder_step(user_goal)
        if first_tester is None:
            _insert_after_leading_analysis(normalized, coder_step)
        else:
            normalized.insert(first_tester, coder_step)
            first_coder = first_tester
            first_tester += 1
    elif first_tester is not None and first_tester < first_coder:
        tester_step = normalized.pop(first_tester)
        first_coder -= 1
        normalized.insert(first_coder + 1, tester_step)
        first_tester = first_coder + 1

    if _first_index_for_agent(normalized, "tester") is None:
        first_coder = _first_index_for_agent(normalized, "coder")
        insert_at = (first_coder + 1) if first_coder is not None else len(normalized)
        normalized.insert(insert_at, _make_default_tester_step())
    return normalized
