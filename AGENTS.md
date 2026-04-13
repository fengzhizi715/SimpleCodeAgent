# AGENTS.md

## 项目概述

本项目是一个用于演示编程智能体演进路径的单仓库工程。

当前仓库采用双版本结构：

- `app/v1`：当前可运行的单 Agent 编程智能体
- `app/v2`：预留给后续多 Agent 编程智能体

本仓库的目标不是做一个“大而全”的 Agent 框架，而是提供一个：

- 清晰
- 可扩展
- 可观测
- 适合教学与演示
- 接近真实工程分层

的编程智能体实现样例。

---

## 当前目标

### `v1` 的目标

`v1` 是一个轻量级、工具驱动、可验证的单 Agent Runtime。

它当前关注：

- LLM Provider 抽象
- Agent Runtime 循环
- Tool 工具系统
- Session Memory
- RAG 文档检索
- Simple Planner
- Trace 可观测性
- CLI 与 HTTP API

它适合处理：

- 代码阅读与解释
- 小工具类生成
- 简单 CRUD 实现
- 小范围代码修复
- 执行测试并分析失败原因

### `v2` 的目标

`v2` 预留给后续多 Agent 编程智能体。

未来可能包括：

- Coordinator / Worker / Reviewer 模式
- 多 Agent 协作编程
- 更复杂的规划与执行编排
- 更强的上下文治理与权限边界

`v2` 应作为独立实现演进，不应直接破坏 `v1` 的稳定性。

---

## 仓库结构原则

### 1. 共享底座与版本实现必须分离

以下模块视为共享底座：

- `app/core`
- `app/contracts`
- `app/db`
- `app/llm`
- `app/trace`
- `app/api`

这些模块负责：

- 配置
- 协议定义
- SQLite 持久化
- LLM Provider 适配
- Trace 记录与查询
- 外部 HTTP 服务入口

以下模块按版本隔离：

- `app/v1/*`
- `app/v2/*`

不要把版本相关实现继续放回顶层。

---

### 2. Agent 必须是 Tool 驱动的

Agent 不直接执行外部动作。

所有外部操作必须通过 Tool 完成，例如：

- 读取文件
- 写入文件
- 搜索代码
- 执行 shell 命令
- 检索文档

Runtime 负责：

- 解析模型输出
- 分发工具调用
- 控制执行循环
- 管理状态与记忆

不得把文件操作、shell 执行等逻辑直接写进 Runtime。

---

### 3. Contract 优先

所有核心数据结构必须在 `app/contracts` 中定义并复用，例如：

- `ChatMessage`
- `ToolSchema`
- `ToolDefinition`
- `ToolCall`
- `ToolResult`
- `RunRequest`
- `RunResult`
- `TraceEvent`
- `PlanStep`

严禁在核心模块边界直接传递裸字典。

模块之间的数据交换应优先使用：

- Pydantic 模型
- 明确的 schema
- 可校验的结构化对象

---

### 4. `v1` Runtime 必须保持简单稳定

`v1` 的 Runtime Loop 应具备：

- 可预测性
- 易调试
- 有步骤上限
- 可容错
- 可追踪

`v1` 不应演进成复杂 workflow 引擎。

如果需要：

- 多 Agent 编排
- 复杂路由
- DAG / Workflow Runtime

应优先在 `app/v2` 中实现，而不是把 `app/v1` 持续堆复杂。

---

### 5. 优先支持“小范围可验证编程任务”

CodeAgent 当前的能力边界是：

可以支持：

- 阅读和理解代码
- 生成小工具类
- 实现简单 CRUD
- 修复局部 bug
- 执行测试和命令验证修改
- 参考已有模块生成相似实现

不追求：

- 全自动软件工程系统
- 大规模架构改造
- 无限范围代码修改
- 自动部署与上线能力

---

### 6. 可观测性是核心能力

每次运行必须可追踪。

当前 Trace 至少应覆盖：

- `run_started`
- `step_started`
- `llm_called`
- `llm_responded`
- `tool_called`
- `tool_result`
- `memory_written`
- `run_finished`
- `run_failed`

Trace 必须可以通过 `run_id` 查询。

如果新增关键流程，也应补充对应 trace 事件。

---

## 模块职责

### `app/core`

负责：

- 配置读取
- 常量
- 日志
- 通用异常

不得包含业务流程。

### `app/contracts`

负责：

- 核心协议定义
- 跨模块统一数据结构

不得掺入具体实现逻辑。

### `app/db`

负责：

- SQLite 连接
- 建表与迁移
- 基础仓储能力

### `app/llm`

负责：

- Provider 抽象
- OpenAI-compatible client
- 响应解析
- tool call 解析

不得包含 Runtime 执行逻辑。

### `app/trace`

负责：

- trace event 定义
- JSONL 记录
- SQLite trace 查询
- timeline 展示

### `app/api`

负责：

- HTTP 接口
- 请求校验
- 依赖注入
- 版本入口路由

### `app/v1/runtime`

负责：

- 单 Agent 主循环
- step 控制
- 终止条件判断
- 工具调度

### `app/v1/tools`

负责：

- 外部动作执行
- 文件系统操作
- shell 命令执行
- 文档检索工具

Tool 应具备：

- 尽量无状态
- 可重复执行
- 明确 schema
- 结构化结果

### `app/v1/memory`

负责：

- 会话级上下文存储
- 最近消息读取
- summary 能力预留

### `app/v1/rag`

负责：

- 文档切分
- embedding 生成
- 向量存储
- 文档检索

### `app/v1/planner`

负责：

- 将复杂任务拆分为步骤
- 输出简单执行计划

### `app/v2`

负责：

- 后续多 Agent 实现
- 更复杂编排与角色协作

当前为预留目录，新增实现时应保持边界独立，不要直接污染 `v1`。

### `scripts`

用于：

- CLI 入口
- Trace 查看
- 文档导入
- Demo 生成
- 本地调试脚本

---

## 编码规范

- 所有代码必须带类型标注
- 核心结构优先使用 Pydantic
- 函数保持小而清晰
- 避免深层继承
- 避免隐式全局状态
- Tool 必须返回结构化结果
- Runtime 异常必须可捕获并转为可追踪结果
- 新增模块时优先考虑是否属于共享底座还是版本实现

---

## 安全边界

Agent 默认不得：

- 删除任意文件
- 执行无限制 shell 命令
- 自动安装依赖
- 自动发起任意网络请求
- 自动执行 git 高风险操作

所有高风险行为必须：

- 通过 Tool 控制
- 有明确边界
- 可通过 Trace 审计

---

## 演进原则

- `v1` 优先保持稳定与可演示
- `v2` 优先承载实验性多 Agent 能力
- 共享能力成熟后，再考虑从 `v1/v2` 上提到顶层共享模块
- 不要为了未来过度抽象
- 也不要让 `v2` 的需求反向污染 `v1`

---

## 本项目的最终目标

本项目的最终目标不是成为“最强 Agent 框架”。

它的目标是：

> 提供一个清晰、可教学、可演进、具备真实工程边界的编程智能体实现样例。
