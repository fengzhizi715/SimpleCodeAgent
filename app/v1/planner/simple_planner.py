"""简单规划器实现。"""

from __future__ import annotations

from app.contracts.planner import PlanStep
from app.v1.planner.base import Planner


class SimplePlanner(Planner):
    """基于规则的简单任务拆解器。"""

    def should_plan(self, task: str) -> bool:
        normalized = task.lower()
        keywords = [
            "新增",
            "工具类",
            "crud",
            "仿照",
            "参考",
            "修复",
            "bug",
            "模块",
            "方法",
            "搜索",
            "总结",
            "测试",
            "失败原因",
            "实现",
            "分析",
            "create",
            "generate",
            "fix",
            "crud",
            "module",
            "search",
            "summarize",
            "test",
            "analyze",
        ]
        return any(keyword in normalized for keyword in keywords) or len(task) >= 18

    def create_plan(self, task: str) -> list[PlanStep]:
        normalized = task.lower()
        if (
            "目录结构" in task
            or "项目结构" in task
            or "目录" in task
            or "project structure" in normalized
            or "directory structure" in normalized
        ):
            return [
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

        if (
            "修复" in task
            or "bug" in normalized
            or "失败" in task
            or "fix" in normalized
        ):
            return [
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

        if "测试" in task or "pytest" in normalized or "失败原因" in task or "test" in normalized:
            return [
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

        if "crud" in normalized or "方法" in task:
            return [
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

        if "仿照" in task or "参考" in task or "similar" in normalized:
            return [
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

        if "搜索" in task or "总结" in task or "search" in normalized or "summarize" in normalized:
            return [
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

        if "工具类" in task or "新增" in task or "create" in normalized:
            return [
                PlanStep(
                    title="梳理需求和约束",
                    description="明确工具类的职责、命名和放置位置。",
                    input_summary=task,
                ),
                PlanStep(
                    title="查看现有模式",
                    description="搜索项目中相似工具类或相关实现作为参考。",
                    input_summary="工具类命名或用途",
                    tool_name="file_search",
                    max_retries=1,
                ),
                PlanStep(
                    title="生成实现代码",
                    description="根据约束给出可直接落地的工具类实现。",
                    input_summary="参考实现与需求",
                ),
                PlanStep(
                    title="执行最小验证",
                    description="运行编译、导入或测试命令验证工具类。",
                    input_summary="生成的代码",
                    tool_name="shell_run",
                    max_retries=1,
                ),
            ]

        return [
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
