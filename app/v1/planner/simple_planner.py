"""简单规划器实现。"""

from __future__ import annotations

from app.contracts.planner import PlanStep
from app.v1.planner.base import Planner


class SimplePlanner(Planner):
    """基于规则的简单任务拆解器。"""

    # 文档检索触发词：中英文对等覆盖
    DOC_RETRIEVAL_KEYWORDS = (
        # English
        "docs",
        "doc ",
        "doc\n",
        "documentation",
        "knowledge base",
        "according to docs",
        # 中文
        "文档",
        "知识库",
        "检索文档",
        "检索相关文档",
        "先查文档",
        "先检索文档",
        "根据 docs",
        "根据文档",
        "根据知识库",
    )

    # should_plan 触发词：中英文对等覆盖
    _PLAN_TRIGGER_KEYWORDS = [
        # 创建/新增类
        "新增", "增加", "工具类", "函数", "实现",
        "create", "generate", "function", "implement", "add",
        # CRUD / 方法类
        "crud", "方法",
        "method", "endpoint", "api",
        # 仿照/参考类
        "仿照", "参考",
        "similar", "imitate", "like the existing", "based on",
        # 修复/Bug 类
        "修复", "bug", "失败原因",
        "fix", "debug", "resolve", "error", "issue",
        # 搜索/总结类
        "搜索", "总结", "分析",
        "search", "summarize", "analyze", "explain", "review",
        # 测试类
        "测试",
        "test", "pytest",
        # 结构/模块类
        "模块", "目录", "目录结构", "项目结构",
        "module", "refactor", "restructure", "directory structure", "project structure",
        # 更新/修改类
        "更新", "修改", "调整",
        "update", "modify", "change", "adjust", "refactor",
    ]

    def should_plan(self, task: str) -> bool:
        normalized = task.lower()
        return any(keyword in normalized for keyword in self._PLAN_TRIGGER_KEYWORDS) or len(task) >= 18

    def create_plan(self, task: str) -> list[PlanStep]:
        normalized = task.lower()
        needs_doc_retrieval = self._needs_doc_retrieval(task, normalized)
        if (
            # 创建/新增类
            "工具类" in task
            or "新增" in task
            or "增加" in task
            or "函数" in task
            or "实现" in task
            or "create" in normalized
            or "function" in normalized
            or "implement" in normalized
            or "add" in normalized
        ):
            plan = [
                PlanStep(
                    title="查看项目结构",
                    description="查看项目根目录，识别代码目录、测试目录和可能的落盘位置。",
                    input_summary=task,
                    tool_name="list_dir",
                    max_retries=1,
                ),
                PlanStep(
                    title="搜索现有代码模式",
                    description="搜索现有实现，提取函数、工具模块和代码风格线索。",
                    input_summary="查找现有实现风格与放置位置",
                    tool_name="file_search",
                    max_retries=1,
                ),
                PlanStep(
                    title="生成待写入实现",
                    description=(
                        "根据项目结构和现有风格，生成可直接写入的实现。"
                        "优先按以下格式输出：先单独给出一行相对路径，例如 "
                        '`path: app/utils/date_utils.py`，然后直接给出完整代码块。'
                        "不要输出工具调用说明，不要解释下一步，不要输出伪 JSON。"
                    ),
                    input_summary="项目结构、代码风格和用户需求",
                ),
                PlanStep(
                    title="写入实现文件",
                    description="将上一步给出的 path 和完整代码内容直接写入工作区文件。",
                    input_summary="上一步输出的路径和代码内容",
                    tool_name="write_file",
                    max_retries=1,
                ),
            ]
            return self._finalize_plan(plan, needs_doc_retrieval)

        if (
            # 结构/目录类
            "目录结构" in task
            or "项目结构" in task
            or "目录" in task
            or "project structure" in normalized
            or "directory structure" in normalized
            or "refactor" in normalized
            or "restructure" in normalized
        ):
            plan = [
                PlanStep(
                    title="查看根目录结构",
                    description="使用目录工具查看项目根目录，识别主要目录和关键文件。",
                    input_summary=task,
                    tool_name="list_dir",
                    max_retries=1,
                ),
                PlanStep(
                    title="读取关键配置文件",
                    description="读取能体现构建方式、入口和模块划分的关键文件。",
                    input_summary="根目录结构与关键文件线索",
                    tool_name="read_file",
                    max_retries=1,
                ),
                PlanStep(
                    title="总结目录与模块组织",
                    description="结合目录和关键文件内容，总结项目结构、模块职责和开发约定。",
                    input_summary="目录结构与关键文件内容",
                ),
            ]
            return self._finalize_plan(plan, needs_doc_retrieval)

        if (
            # 修复/Bug 类
            "修复" in task
            or "bug" in normalized
            or "失败" in task
            or "fix" in normalized
            or "debug" in normalized
            or "resolve" in normalized
            or "error" in normalized
            or "issue" in normalized
        ):
            plan = [
                PlanStep(
                    title="复现问题",
                    description="先运行最小验证命令，确认当前错误表现。",
                    input_summary=task,
                    tool_name="shell_run",
                    max_retries=1,
                ),
                PlanStep(
                    title="定位相关实现",
                    description="搜索并阅读与错误相关的代码和测试。",
                    input_summary="失败输出或报错线索",
                    tool_name="file_search",
                    max_retries=1,
                ),
                PlanStep(
                    title="实施小范围修复",
                    description="基于错误原因做最小代码修改。",
                    input_summary="相关实现与失败原因",
                ),
                PlanStep(
                    title="重新验证修复",
                    description="再次运行验证命令，确认问题已解决。",
                    input_summary="修复后的代码",
                    tool_name="shell_run",
                    max_retries=1,
                ),
            ]
            return self._finalize_plan(plan, needs_doc_retrieval)

        if (
            # 测试类
            "测试" in task
            or "pytest" in normalized
            or "失败原因" in task
            or "test" in normalized
        ):
            plan = [
                PlanStep(
                    title="定位测试入口",
                    description="识别应该执行的测试命令或相关测试文件。",
                    input_summary=task,
                ),
                PlanStep(
                    title="执行测试",
                    description="运行测试并收集失败输出。",
                    input_summary="测试命令或测试文件",
                    tool_name="shell_run",
                    max_retries=1,
                ),
                PlanStep(
                    title="分析失败原因",
                    description="根据测试输出和相关代码总结失败原因。",
                    input_summary="测试输出",
                ),
            ]
            return self._finalize_plan(plan, needs_doc_retrieval)

        if (
            # CRUD / 方法类
            "crud" in normalized
            or "方法" in task
            or "method" in normalized
            or "endpoint" in normalized
        ):
            plan = [
                PlanStep(
                    title="查看服务接口与数据结构",
                    description="读取现有 service 和相关模型，明确缺失的方法。",
                    input_summary=task,
                    tool_name="read_file",
                    max_retries=1,
                ),
                PlanStep(
                    title="搜索相似实现",
                    description="搜索项目中相似的 CRUD 或 service 代码模式。",
                    input_summary="service 名称或方法名",
                    tool_name="file_search",
                    max_retries=1,
                ),
                PlanStep(
                    title="实现缺失的 CRUD 方法",
                    description="按现有风格补充目标方法。",
                    input_summary="接口、数据结构与参考实现",
                ),
                PlanStep(
                    title="运行验证命令",
                    description="执行针对该 service 的测试或最小验证命令。",
                    input_summary="修改后的 service",
                    tool_name="shell_run",
                    max_retries=1,
                ),
            ]
            return self._finalize_plan(plan, needs_doc_retrieval)

        if (
            # 仿照/参考类
            "仿照" in task
            or "参考" in task
            or "similar" in normalized
            or "imitate" in normalized
            or "like the existing" in normalized
            or "based on" in normalized
        ):
            plan = [
                PlanStep(
                    title="阅读参考模块",
                    description="读取已有模块，提取结构、接口和代码风格。",
                    input_summary=task,
                    tool_name="read_file",
                    max_retries=1,
                ),
                PlanStep(
                    title="明确新模块差异",
                    description="梳理新模块与参考模块的名称和字段差异。",
                    input_summary="参考模块内容",
                ),
                PlanStep(
                    title="生成相似模块",
                    description="按相同风格实现新的模块。",
                    input_summary="参考模块与差异说明",
                ),
                PlanStep(
                    title="验证生成结果",
                    description="通过测试、导入或编译命令验证新模块。",
                    input_summary="新模块实现",
                    tool_name="shell_run",
                    max_retries=1,
                ),
            ]
            return self._finalize_plan(plan, needs_doc_retrieval)

        if (
            # 搜索/总结/分析类
            "搜索" in task
            or "总结" in task
            or "分析" in task
            or "search" in normalized
            or "summarize" in normalized
            or "analyze" in normalized
            or "explain" in normalized
            or "review" in normalized
        ):
            plan = [
                PlanStep(
                    title="定位相关代码",
                    description="搜索与目标功能相关的文件、函数或类。",
                    input_summary=task,
                    tool_name="file_search",
                    max_retries=1,
                ),
                PlanStep(
                    title="阅读关键实现",
                    description="读取最关键的实现文件，提取必要上下文。",
                    input_summary="搜索结果",
                    tool_name="read_file",
                    max_retries=1,
                ),
                PlanStep(
                    title="总结功能行为",
                    description="结合搜索和代码内容输出结论。",
                    input_summary="相关代码上下文",
                ),
            ]
            return self._finalize_plan(plan, needs_doc_retrieval)

        plan = [
            PlanStep(
                title="理解任务",
                description="提取任务目标、约束与预期输出。",
                input_summary=task,
            ),
            PlanStep(
                title="执行关键步骤",
                description="完成主要实现或分析动作。",
                input_summary="任务目标与约束",
            ),
            PlanStep(
                title="总结结果",
                description="整理最终结论、产物或建议。",
                input_summary="执行结果",
            ),
        ]
        return self._finalize_plan(plan, needs_doc_retrieval)

    def _needs_doc_retrieval(self, task: str, normalized: str) -> bool:
        """判断任务是否应在规划前强制插入文档检索。"""
        del task
        return any(keyword in normalized for keyword in self.DOC_RETRIEVAL_KEYWORDS)

    def _finalize_plan(self, plan: list[PlanStep], needs_doc_retrieval: bool) -> list[PlanStep]:
        """按统一规则补充必须的前置步骤。"""
        if not needs_doc_retrieval:
            return plan
        if any(step.tool_name == "retrieve_docs" for step in plan):
            return plan
        return [self._build_doc_retrieval_step(), *plan]

    def _build_doc_retrieval_step(self) -> PlanStep:
        """构建统一的文档检索步骤。"""
        return PlanStep(
            title="检索相关文档",
            description="先从知识库中检索与任务相关的文档片段，提取实现约定、接口说明和背景知识。",
            input_summary="用户任务与文档约束",
            tool_name="retrieve_docs",
            max_retries=1,
        )
