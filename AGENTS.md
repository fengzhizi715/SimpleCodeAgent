# AGENTS.md

## 项目概述

本项目是一个用于演示 **编程智能体工程化演进路径** 的单仓库示例工程。

仓库采用 **三版本并行演进** 结构：

- `app/v1`：单 Agent 编程智能体，实现基础课程配套代码
- `app/v2`：中心化多 Agent 编程智能体，实现高级课程配套代码
- `app/v3`：Graph + Skill + Trigger 驱动的新一代运行时，用于展示从“多 Agent 编排”继续演进到“结构化执行内核”的路径

本仓库的目标不是构建一个“大而全”的通用 Agent 框架，而是提供一个：

- 清晰
- 可运行
- 可扩展
- 可观测
- 适合教学与演示
- 接近真实工程分层

的编程智能体实现样例。

本仓库同时承担三类职责：

1. **课程样例工程**
   - `v1` 对应单智能体基础课程
   - `v2` 对应多智能体高级课程
   - `v3` 对应结构化 Runtime / Graph / Skill 演进阶段

2. **演进型工程骨架**
   - 展示从单 Agent 到多 Agent 的合理升级路径
   - 展示从中心化多 Agent 到 Graph Runtime 的升级路径
   - 展示共享底座与版本实现如何共存
   - 展示在不破坏旧版本稳定性的前提下持续演进系统

3. **工程边界示例**
   - 展示 Tool / Agent / Skill / Trigger 三类抽象如何分层
   - 展示版本实验如何在仓库内共存，而不是互相覆盖

---

## 版本定位

### `v1` 的定位

`v1` 是一个 **轻量、工具驱动、可验证、可教学** 的单 Agent Runtime。

它服务于基础课程，重点讲清楚一个编程智能体最核心的能力闭环。

当前仓库级只要求明确：

- `v1` 是单 Agent、Tool 驱动、教学优先的稳定版本
- `v1` 必须长期保持可独立运行、可独立教学
- `v1` 不依赖 `v2`、`v3`
- `v1` 的详细约束、模块职责与演进边界以下级文档为准：
  - `app/v1/AGENTS.md`

---

### `v2` 的定位

`v2` 是一个 **中心化多 Agent 编排版 CodeAgent**，服务于高级课程。

它不是对 `v1` 的直接覆盖，也不是把 `v1` 持续堆复杂，而是站在 `v1` 的工程基础之上，演进出中心化多 Agent 能力。

当前仓库级只要求明确：

- `v2` 是中心化多 Agent 编排方向，而不是 `v1` 的替换版
- `v2` 聚焦可控协作、结构化委派与失败收敛
- `v2` 不应承接无边界事件驱动或去中心化协作复杂度
- `v2` 的详细约束、模块职责与演进边界以下级文档为准：
  - `app/v2/AGENTS.md`

---

### `v3` 的定位

`v3` 是一个 **Graph + Skill + Trigger 驱动的结构化运行时**。

它的目标不是简单地“再增加几个 Agent”，而是把系统演进到新的抽象层。

当前仓库级只要求明确：

- `v3` 是结构化执行内核方向，而不是 `v2` 的直接加料版
- `v3` 可以通过 adapter 复用 `v1` / `v2` 的稳定能力
- `v3` 的详细约束、模块职责与演进边界以下级文档为准：
  - `app/v3/AGENTS.md`

---

## 多版本共存原则

### 1. `v1`、`v2`、`v3` 必须长期共存

三个版本不是“旧版本 / 新版本”的简单替换关系，而是：

- 三套可以并行存在的实现
- 三个不同演进阶段的教学与工程样例
- 同一仓库中的三条能力演进线

因此必须遵守：

- 不得为了实现 `v2` 或 `v3` 而破坏 `v1`
- 不得把 `v3` 的 graph / trigger 复杂度强行塞回 `v2`
- 不得让 `v1` 依赖 `v2` 或 `v3`
- 不得让 `v2` 反向依赖 `v3` 的实验性运行时
- `v2` 可以复用共享底座，也可以参考 `v1` 的成熟实现
- `v3` 可以通过 adapter 复用 `v1 tools` 与 `v2 agent` 能力，但应保持自身运行时边界独立
- 当某些能力被验证为稳定通用后，可考虑上提到共享层

---

### 2. 共享底座与版本实现必须严格分离

以下模块视为 **共享底座**：

- `app/core`
- `app/contracts`
- `app/db`
- `app/llm`
- `app/trace`
- `app/api`

这些模块负责通用能力，例如：

- 配置
- 协议定义
- SQLite 持久化
- LLM Provider 抽象与适配
- Trace 记录与查询
- 外部 HTTP 服务入口

以下模块属于 **版本实现层**：

- `app/v1/*`
- `app/v2/*`
- `app/v3/*`

版本实现层负责各自的：

- Runtime
- Planner / Graph Builder
- Memory / Workspace / ExecutionContext
- Tools / Agents / Skills 绑定
- Prompt 组织
- 具体执行流程
- 版本特定的上下文治理策略

不要把版本特定逻辑继续回灌到顶层共享目录。

---

### 3. 共享能力应通过“成熟后上提”的方式演进

允许在 `v1`、`v2` 或 `v3` 中先落地实现某项能力，再视成熟度决定是否上提为共享模块。

演进顺序应优先遵循：

1. 在具体版本中验证需求与边界
2. 保持实现可运行、可教学
3. 确认该能力确实适用于多个版本
4. 再上提到共享层

不要为了“未来可能复用”而过度抽象，也不要把尚未稳定的实验性能力提前放入共享层。

---

## 当前目标

### `v1` 的当前目标

`v1` 是一个轻量级、工具驱动、可验证的单 Agent Runtime。

仓库级目标只要求：

- `v1` 保持轻量、稳定、可验证
- `v1` 持续服务单 Agent 教学闭环
- 具体实现规则、模块职责和演进约束以下级文档为准：
  - `app/v1/AGENTS.md`

---

### `v2` 的当前目标

`v2` 是中心化多 Agent 编程智能体。

仓库级目标只要求：

- `v2` 作为独立实现继续演进
- `v2` 聚焦中心化多 Agent 编排
- 不直接破坏 `v1` 的稳定性与课程边界
- 具体实现规则、模块职责和演进约束以下级文档为准：
  - `app/v2/AGENTS.md`

---

### `v3` 的当前目标

`v3` 是 Graph Runtime + Skill Runtime 的结构化执行版本。

仓库级目标只要求：

- `v3` 作为独立实现继续演进
- 不直接破坏 `v1` / `v2` 的稳定性与课程边界
- 具体实现规则、模块职责和演进约束以下级文档为准：
  - `app/v3/AGENTS.md`

---

## 核心设计原则

### 1. Agent / Skill 必须是受控执行单元

`v1` / `v2` 中的 Agent 不直接执行外部动作。

所有外部操作必须通过 Tool 完成，例如：

- 读取文件
- 写入文件
- 搜索代码
- 执行 shell 命令
- 检索文档
- 运行测试

对于 `v3`：

- Skill 是执行单元
- Tool Skill 仍应通过受控 adapter 访问外部能力
- Composite Skill 负责组织执行，不应内嵌无边界副作用

Runtime、Orchestrator 或 Execution Kernel 负责：

- 解析模型输出
- 分发工具调用或 skill 执行
- 控制执行循环或 graph 执行
- 管理状态、上下文与记忆
- 跟踪执行过程

不得把文件操作、shell 执行等外部行为直接写进 Runtime、Agent、Skill 或 Orchestrator 主逻辑中。

---

### 2. Contract 优先

所有核心数据结构必须优先在共享 `app/contracts` 或版本内 `contracts` 中定义并复用。

例如共享层：

- `ChatMessage`
- `ToolSchema`
- `ToolDefinition`
- `ToolCall`
- `ToolResult`
- `RunRequest`
- `RunResult`
- `TraceEvent`
- `PlanStep`

对于 `v2`，应优先使用结构化对象，例如：

- `AgentSpec`
- `AgentTask`
- `AgentResult`
- `DelegationRecord`
- `SharedWorkspace`
- `ExecutionNode`

对于 `v3`，应优先使用结构化对象，例如：

- `TaskGraph`
- `TaskNode`
- `SkillSpec`
- `SkillInput`
- `SkillOutput`
- `TriggerRule`
- `V3Event`
- `ExecutionReport`

严禁在核心模块边界传递裸字典。

模块之间的数据交换应优先使用：

- Pydantic 模型
- 明确 schema
- 可校验的结构化对象

---

### 3. `v1` / `v2` / `v3` 必须各守边界

版本间的核心边界是：

- `v1` 保持单 Agent、简单稳定、教学友好
- `v2` 保持中心化多 Agent、可控、可收敛
- `v3` 保持 Graph / Skill / Trigger 结构化运行时方向

更细的版本内约束以下级文档为准：

- `app/v1/AGENTS.md`
- `app/v2/AGENTS.md`
- `app/v3/AGENTS.md`

---

### 4. 优先支持“小范围、可验证”的编程任务

当前仓库聚焦的能力边界是：

可以支持：

- 阅读和理解代码
- 生成小工具类
- 实现简单 CRUD
- 修复局部 bug
- 执行测试和命令验证修改
- 参考已有模块生成相似实现
- 生成小规模 graph 任务并顺序执行

不追求：

- 全自动软件工程系统
- 大规模架构重构
- 无限范围代码修改
- 自动部署与上线
- 无边界自治执行

---

### 5. 可观测性是核心能力，而不是附加能力

每次运行都必须可追踪、可定位、可解释。

当前共享 Trace 至少应覆盖：

- `run_started`
- `step_started`
- `llm_called`
- `llm_responded`
- `tool_called`
- `tool_result`
- `memory_written`
- `run_finished`
- `run_failed`

对于 `v1` / `v2` / `v3`，更细的 trace / event 约束以下级文档为准：

- `app/v1/AGENTS.md`
- `app/v2/AGENTS.md`
- `app/v3/AGENTS.md`

对于 `v3`，事件与 trace 设计的详细要求以下级文档为准：

- `app/v3/AGENTS.md`

Trace 或事件记录必须可以通过 `run_id` 查询。

如果新增关键流程，应同步补充对应 trace / event 记录。

---

## 模块职责

### `app/core`

负责：

- 配置读取
- 常量
- 日志
- 通用异常
- 通用工具函数

不得包含具体业务流程。

---

### `app/contracts`

负责：

- 核心协议定义
- 跨模块统一数据结构
- 版本共用的结构化对象

不得掺入具体实现逻辑。

---

### `app/db`

负责：

- SQLite 连接
- 建表与迁移
- 基础仓储能力
- 通用持久化支持

---

### `app/llm`

负责：

- Provider 抽象
- OpenAI-compatible Client
- 响应解析
- Tool Call 解析

不得包含 Runtime 或 Agent 编排逻辑。

---

### `app/trace`

负责：

- Trace Event 定义
- JSONL 记录
- SQLite Trace 查询
- Timeline 展示
- 执行记录落库与检索

---

### `app/api`

负责：

- HTTP 接口
- 请求校验
- 依赖注入
- 版本入口路由

`api` 应负责把外部请求分发到对应版本实现，不应承载版本内部业务流程。

---

### `app/v1`

`v1` 的详细模块职责、Runtime / Tool / Memory / RAG / Planner 约束和演进边界以下级文档为准：

- `app/v1/AGENTS.md`

---

### `app/v2`

`v2` 的详细模块职责、Orchestrator / Agent / Workspace / Replay 约束和演进边界以下级文档为准：

- `app/v2/AGENTS.md`

---

### `app/v3`

`v3` 的详细模块职责、Skill / Trigger 约束、事件模型和演进边界以下级文档为准：

- `app/v3/AGENTS.md`

---

### `scripts`

用于：

- CLI 入口
- Trace 查看
- 文档导入
- Demo 生成
- 本地调试脚本

脚本应服务于开发、调试与演示，不应替代正式 Runtime 逻辑。

---

## 编码规范

- 所有代码必须带类型标注
- 核心结构优先使用 Pydantic
- 函数保持小而清晰
- 避免深层继承
- 避免隐式全局状态
- Tool / Agent / Skill 必须返回结构化结果
- Runtime 异常必须可捕获并转为可追踪结果
- 版本边界必须清晰
- 新增模块时，优先判断它属于：
  - 共享底座
  - `v1`
  - `v2`
  - `v3`

不要让“临时方便”破坏层次边界。

---

## 安全边界

Agent 或 Skill 默认不得：

- 删除任意文件
- 执行无限制 shell 命令
- 自动安装依赖
- 自动发起任意网络请求
- 自动执行 git 高风险操作

所有高风险行为必须：

- 通过 Tool、Adapter 或受控执行层控制
- 有明确边界
- 可配置
- 可通过 Trace / Event 审计

对于 `v1` / `v2` / `v3`，更细的高风险行为约束以下级文档为准：

- `app/v1/AGENTS.md`
- `app/v2/AGENTS.md`
- `app/v3/AGENTS.md`

对于 `v3`，高风险行为的详细约束以下级文档为准：

- `app/v3/AGENTS.md`

---

## 演进原则

- `v1` 优先保持稳定、简单、可演示
- `v2` 优先承载中心化多 Agent 协作能力
- `v3` 优先承载 Graph / Skill / Trigger 结构化运行时能力
- 更细的版本内演进约束以下级文档为准：
  - `app/v1/AGENTS.md`
  - `app/v2/AGENTS.md`
  - `app/v3/AGENTS.md`
- 共享能力成熟后，再考虑从 `v1/v2/v3` 上提到顶层共享模块
- 不要为了未来过度抽象
- 也不要让新版本需求反向污染旧版本

---

## 本项目的最终目标

本项目的最终目标不是成为“最强 Agent 框架”。

它的目标是：

> 提供一个清晰、可教学、可演进、具备真实工程边界的编程智能体实现样例。

更进一步说，本项目希望回答三个问题：

1. 如何从零实现一个可运行的单 Agent CodeAgent
2. 如何在不破坏原有系统的前提下，把它演进成一个工程化的多 Agent 系统
3. 如何继续把多 Agent 系统演进成一个结构化、可追踪、可扩展的 Graph Runtime
