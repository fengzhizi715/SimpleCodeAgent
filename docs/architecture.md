# 架构说明

本文档面向准备继续维护或扩展本项目的开发者，重点说明当前 `v1` 的主链路、模块边界，以及后续 `v2` 应如何接入。

## 1. 当前架构概览

项目采用“共享底座 + 版本实现”的目录结构：

- `app/core`
  - 配置、日志、异常等基础能力
- `app/contracts`
  - 跨模块共享的数据结构，例如 `ChatMessage`、`RunResult`、`ToolResult`
- `app/db`
  - SQLite 连接、建表与基础仓储能力
- `app/llm`
  - Provider 抽象与 OpenAI-compatible 适配
- `app/trace`
  - Trace 事件定义、JSONL 落盘、SQLite 索引与 timeline 查询
- `app/api`
  - FastAPI 入口、路由和依赖装配
- `app/v1`
  - 当前单 Agent 版本实现
- `app/v2`
  - 后续多 Agent 编程智能体预留目录

这套结构的核心意图是：

- 共享协议和基础设施保持稳定
- `v1` 作为可运行、可演示的单 Agent 版本持续可用
- `v2` 在不破坏 `v1` 的前提下逐步演进为多 Agent 实现

## 2. v1 主链路

一次典型的 `v1` 运行流程如下：

1. CLI 或 API 接收任务输入
2. 根据参数与环境变量构造 `LLMProvider`
3. 初始化 `ToolRegistry`、`SessionMemory`、`TraceRecorder`
4. `AgentLoop` 载入历史消息，组装本轮上下文
5. `RuntimeExecutor` 调用模型
6. Runtime 判断模型结果：
   - 如果是普通回答，则结束运行
   - 如果包含 tool call，则执行工具并将结果回填给下一轮模型
   - 如果出现异常结果，则返回可追踪的 fallback answer
7. 运行结束后写入：
   - session memory
   - run metadata
   - trace timeline

## 3. Planner 与普通单轮运行的关系

`v1` 不做复杂 workflow runtime，但已经把“主循环”和“规划步骤执行”拆成了不同职责：

- 简单任务：
  - 直接进入 `AgentLoop.run()`
- 复杂任务：
  - 先由 `SimplePlanner` 拆成 2 到 5 个步骤
  - 再由 `PlanExecutor` 顺序执行每个步骤
  - 最后再调用一次汇总步骤，生成最终答案

当前 `app/v1/runtime` 内部的职责大致如下：

- `loop.py`
  - 只负责单 Agent 主循环、工具回填、fallback 和 run 级持久化
- `plan_executor.py`
  - 负责规划步骤执行、步骤汇总、写入成功校验
- `direct_tool_executor.py`
  - 负责对明确步骤做 deterministic tool execution
- `write_intent_parser.py`
  - 负责从模型输出中提取 `path/content` 等写入意图

这样做的目标不是把 `v1` 变复杂，而是避免把规划、写入解析和主循环全部堆在一个文件里，降低调试成本。

## 4. Tool 系统设计

本项目的 Agent 是 Tool 驱动的。

Runtime 不直接操作文件系统，也不直接执行 shell。所有外部动作都必须通过 Tool 完成，例如：

- `read_file`
- `file_search`
- `write_file`
- `shell_run`
- `retrieve_docs`

这样设计的好处是：

- 权限边界更清楚
- 行为更容易审计
- 工具失败可以统一回填给模型处理
- 后续 `v2` 可以复用相同的工具协议

当前 `ToolRegistry` 还支持配置工作目录，用于分析指定本地项目目录，而不是只分析当前仓库。

在顶层输入语义上，项目现在统一使用 `workdir`：

- CLI / 模块入口使用 `--workdir`
- API 使用 `workdir`
- `project_root` 仅作为历史兼容输入名保留

## 5. Memory 与 Session 的边界

本项目中有两个容易混淆的概念：

- `run_id`
  - 表示一次具体执行
  - 每次运行都会生成新的 `run_id`
- `session_id`
  - 表示同一个会话上下文
  - 只有 `session_id` 相同，前后两次对话才会共享会话历史

`v1` 当前采用“会话级最近消息记忆”：

- 每次运行前，先从 SQLite 读取该 `session_id` 最近历史
- 运行完成后，再把本轮新增的 `user/assistant/tool` 消息写回

规划任务内部的中间步骤默认不会直接污染主会话记忆，只会把最终汇总结果回写到主会话。

## 6. Trace 体系

每次运行至少会记录这些事件：

- `run_started`
- `step_started`
- `llm_called`
- `llm_responded`
- `tool_called`
- `tool_result`
- `memory_written`
- `run_finished`
- `run_failed`

Trace 同时保留两种形式：

- `.traces/<run_id>.jsonl`
  - 适合直接查看单次运行详情
- SQLite `trace_index`
  - 适合按 `run_id` 做时间线查询

## 7. 存储结构

当前项目存在两套持久化：

- 主业务库：`.simple_code_agent.sqlite3`
  - 保存 sessions、messages、runs、trace metadata、summary
- 向量库：`.chroma/chroma.sqlite3`
  - 保存 RAG 文档向量与检索索引

这种拆分是有意为之：

- 主业务数据统一落到 SQLite
- 向量检索仍交给 Chroma 处理

## 8. 为什么 v1 和 v2 要分目录

这是当前仓库最重要的演进约束之一。

`v1` 和 `v2` 的差异不会只是“功能多一点”或“提示词复杂一点”，而是运行模型本身不同：

- `v1` 是单 Agent loop
- `v2` 计划演进成多 Agent 编排

因此：

- `runtime/planner/tools/rag/memory` 这类实现必须按版本隔离
- 不应把 `v2` 的复杂编排直接堆进 `app/v1`
- 成熟且稳定的能力，才考虑从 `v1/v2` 上提到共享底座

## 9. 开发建议

如果你要继续扩展项目，建议优先遵循下面几条：

- 新增共享协议时，优先放到 `app/contracts`
- 新增数据库表或索引时，统一走 `app/db`
- 新增 `v1` 能力时，优先保持简单可调试，不要把它做成 workflow 引擎
- 新增 `v2` 能力时，尽量通过清晰的 agent role 和 contract 做边界隔离
- 新增工具时，优先保证结构化输入输出，而不是先堆复杂逻辑

## 10. 后续推荐阅读

- [README.md](/Users/tony/PycharmProjects/SimpleCodeAgent/README.md)
- [docs/usage_guide.md](/Users/tony/PycharmProjects/SimpleCodeAgent/docs/usage_guide.md)
- [AGENTS.md](/Users/tony/PycharmProjects/SimpleCodeAgent/AGENTS.md)
