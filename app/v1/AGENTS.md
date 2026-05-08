# AGENTS.md

## 适用范围

本文件用于约束 `app/v1` 目录下的设计、实现与演进。

当修改以下目录时，应优先遵守本文件：

- `app/v1/runtime`
- `app/v1/tools`
- `app/v1/memory`
- `app/v1/rag`
- `app/v1/planner`

如果与仓库根目录 `AGENTS.md` 存在交叉：

- 根目录 `AGENTS.md` 负责仓库级原则
- 本文件负责 `v1` 目录级细化约束

---

## v1 定位

`v1` 是一个 **轻量、工具驱动、可验证、可教学** 的单 Agent Runtime。

它服务于基础课程，重点讲清楚一个编程智能体最核心的能力闭环，包括：

- LLM Provider 抽象
- Agent Runtime Loop
- Tool 工具系统
- Session Memory
- RAG 文档检索
- Simple Planner
- Trace 可观测性
- CLI 与 HTTP API

`v1` 的设计目标是：

- 简单
- 稳定
- 易调试
- 易理解
- 易演示

它适合处理：

- 代码阅读与解释
- 小工具类生成
- 简单 CRUD 实现
- 小范围代码修复
- 执行测试并分析失败原因

`v1` 必须长期保持：

- 可独立运行
- 可独立教学
- 不依赖 `v2`
- 不依赖 `v3`
- 不因后续版本演进而被破坏

---

## 当前目标

`v1` 当前关注：

- 单 Agent 主循环
- Tool 调用与结果处理
- 小范围编程任务闭环
- 会话上下文管理
- 简单规划与步骤控制
- RAG 检索支持
- Trace 可观测性
- CLI 与 HTTP API 演示入口

`v1` 的优化方向应始终围绕：

- 稳定性
- 可预测性
- 教学清晰度
- 演示完整性

---

## 核心设计原则

### 1. Agent 必须是 Tool 驱动的

`v1` 中的 Agent 不直接执行外部动作。

所有外部操作必须通过 Tool 完成，例如：

- 读取文件
- 写入文件
- 搜索代码
- 执行 shell 命令
- 检索文档
- 运行测试

Runtime 负责：

- 解析模型输出
- 分发工具调用
- 控制执行循环
- 管理状态、上下文与记忆
- 跟踪执行过程

不得把文件操作、shell 执行等外部行为直接写进 Runtime 主逻辑中。

---

### 2. `v1` 必须保持简单稳定

`v1` 的 Runtime Loop 应具备：

- 可预测性
- 易调试
- 步骤上限
- 错误可收敛
- Trace 完整

`v1` 不应继续演进成复杂 workflow 引擎，也不应被改造成多 Agent 编排器。

如果需要：

- 多 Agent 调度
- 复杂角色分工
- Delegation / Handoff
- 更复杂的上下文治理
- DAG / Workflow / Event-driven Runtime

应优先在 `app/v2` 或 `app/v3` 中实现。

---

### 3. Contract 优先

`v1` 应优先复用共享层结构化对象，例如：

- `ChatMessage`
- `ToolSchema`
- `ToolDefinition`
- `ToolCall`
- `ToolResult`
- `RunRequest`
- `RunResult`
- `TraceEvent`
- `PlanStep`

严禁在核心模块边界长期传递裸字典。

---

### 4. 优先支持小范围、可验证的编程任务

`v1` 当前聚焦：

- 阅读和理解代码
- 小范围代码修改
- 小工具生成
- 执行测试并解释失败

`v1` 不追求：

- 多 Agent 协作
- 复杂工作流编排
- 无边界自治执行

---

### 5. 可观测性必须完整

`v1` 的 Trace 至少应覆盖：

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

---

## 模块职责

### `app/v1/runtime`

负责：

- 单 Agent 主循环
- Step 控制
- 终止条件判断
- Tool 调度
- 简单错误处理与结果收敛

---

### `app/v1/tools`

负责：

- 外部动作执行
- 文件系统操作
- Shell 命令执行
- 文档检索工具
- 编程任务需要的基础工具集合

Tool 应具备：

- 尽量无状态
- 可重复执行
- 明确 schema
- 结构化结果

---

### `app/v1/memory`

负责：

- 会话级上下文存储
- 最近消息读取
- 摘要记忆能力预留

---

### `app/v1/rag`

负责：

- 文档切分
- Embedding 生成
- 向量存储
- 文档检索

---

### `app/v1/planner`

负责：

- 将复杂任务拆分为简单步骤
- 输出单 Agent 可执行的简单计划

---

## 编码规范

- 所有代码必须带类型标注
- 核心结构优先使用 Pydantic
- 函数保持小而清晰
- 避免深层继承
- 避免隐式全局状态
- Tool 必须返回结构化结果
- Runtime 异常必须可捕获并转为可追踪结果

新增模块时，优先判断它属于：

- `runtime`
- `tools`
- `memory`
- `rag`
- `planner`

不要让临时方便破坏 `v1` 的教学边界。

---

## 安全边界

`v1` 默认不得：

- 删除任意文件
- 执行无限制 shell 命令
- 自动安装依赖
- 自动发起任意网络请求
- 自动执行 git 高风险操作

所有高风险行为必须：

- 通过 Tool 控制
- 有明确边界
- 可配置
- 可通过 Trace 审计

---

## 演进原则

- `v1` 优先保持稳定、简单、可演示
- 不要把 `v1` 堆成复杂 workflow 引擎
- 不要为了兼容 `v2` / `v3` 反向增加 `v1` 复杂度
- 共享能力成熟后，再考虑上提到共享层
