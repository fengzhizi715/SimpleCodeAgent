# Agent Runtime

CodeAgent v1 是一个轻量级的工具驱动 Agent Runtime。

核心约束：

- Agent 不直接执行外部动作
- 所有文件、Shell、检索操作都通过 Tool 完成
- Runtime 负责循环控制、状态管理、错误容错和 trace 记录

如果问题需要资料支持，Agent 应优先调用 `retrieve_docs` 获取文档上下文。
