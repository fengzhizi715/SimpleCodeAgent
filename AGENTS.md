# AGENTS.md

## 项目概述

本项目实现 **CodeAgent v1 —— 一个轻量级、基于工具驱动的 AI 编程智能体运行时系统（Agent Runtime）。**

项目目标是从零构建一个可扩展、可观测、具备简单编程执行能力的 Agent 系统，包括：

* LLM Provider 抽象
* Agent Runtime 循环
* Tool 工具系统
* Memory 会话记忆
* RAG 文档检索能力
* 简单 Planner 任务拆解
* Trace 可观测性系统
* CLI 与 HTTP 服务接口

本项目适用于：

* 学习 Agent 工程方法论
* 构建 AI 编程助手
* 作为最小 Agent Runtime 的工程参考实现

---

## 架构设计原则

### 1. Agent 必须是 Tool 驱动的

Agent 不直接执行外部操作。

所有外部动作必须通过 Tool 完成，例如：

* 读取文件
* 写入文件
* 搜索代码
* 执行 shell 命令
* 检索文档

Runtime 负责：

* 解析模型输出
* 分发工具调用
* 控制执行循环
* 管理状态与记忆

---

### 2. Contract 优先

所有核心数据结构必须在 `contracts/` 中定义并复用，例如：

* Message
* ToolDefinition
* ToolCall
* ToolResult
* RunRequest / RunResult
* TraceEvent
* PlanStep

严禁在模块之间随意传递裸字典。

---

### 3. Runtime 必须保持简单稳定

Agent Runtime Loop 应具备：

* 可预测性
* 易调试
* 有步骤上限（step-bounded）
* 能容错（failure tolerant）

本项目不引入：

* 多 Agent 编排
* Workflow 引擎
* DAG 调度系统

这些属于更高级系统能力，应在其他项目中实现。

---

### 4. 优先支持“小范围可验证编程任务”

CodeAgent 的能力边界：

可以支持：

* 阅读和理解代码
* 生成小工具类
* 实现简单 CRUD 逻辑
* 修复局部 bug
* 执行测试或命令进行验证

不追求：

* 全自动软件工程系统
* 大规模架构重构
* 跨模块复杂改动
* 自动上线部署能力

---

### 5. 可观测性是核心能力

每一次 Agent 运行必须可追踪。

系统需要记录结构化事件，例如：

* run_started
* llm_called
* llm_response_received
* tool_called
* tool_result
* memory_updated
* run_finished
* run_failed

Trace 必须可以通过 `run_id` 查询。

---

## 模块职责划分

### `llm/`

负责：

* 模型调用
* OpenAI-compatible client
* 响应解析
* 工具调用解析

不得包含 Runtime 执行逻辑。

---

### `runtime/`

负责：

* Agent 主循环
* step 控制
* 终止条件判断
* 工具调度

不得包含具体 Tool 实现。

---

### `tools/`

负责：

* 外部动作执行
* 文件系统访问
* shell 命令执行
* 文档检索

Tool 应具备：

* 无状态
* 可重复执行
* 明确 schema

---

### `memory/`

负责：

* 会话级上下文存储
* 最近对话检索
* 可扩展 summary 能力

---

### `rag/`

负责：

* 文档切分
* embedding 生成
* 向量检索

---

### `planner/`

负责：

* 将复杂任务拆分为步骤
* 生成简单执行计划

---

### `trace/`

负责：

* 记录运行事件
* 存储 trace 元数据
* 提供 trace 查询工具

---

### `api/`

负责：

* HTTP 接口
* 请求校验
* 依赖注入

---

### `scripts/`

用于：

* CLI 入口
* 调试工具
* 数据导入脚本

---

## 编码规范

* 所有代码必须使用类型标注（type hints）
* 核心结构优先使用 Pydantic 定义
* 函数应保持小而清晰
* 避免深层继承结构
* 避免隐式全局状态
* Tool 必须返回结构化结果
* Runtime 所有异常必须可捕获并记录日志

---

## 安全边界

Agent 默认不得：

* 删除任意文件
* 执行无限制 shell 命令
* 自动安装依赖
* 自动执行网络请求
* 自动执行 git 操作

所有高风险行为必须：

* 通过 Tool 控制
* 明确开启
* 可通过 Trace 审计

---

## 可扩展方向（未来能力）

未来可能扩展：

* 多 Agent 协作
* Workflow / DAG Runtime
* 高级 Memory 系统
* 权限治理
* UI 控制面板

这些能力不属于当前最小 Runtime 范畴，应作为独立模块或独立项目实现。

---

## 本项目的最终目标

本项目并不追求成为最强的 Agent 框架。

它的目标是：

> 提供一个清晰、可教学、接近真实生产工程的 Agent Runtime 实现示例。
