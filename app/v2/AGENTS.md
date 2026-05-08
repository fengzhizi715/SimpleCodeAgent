# AGENTS.md

## 适用范围

本文件用于约束 `app/v2` 目录下的设计、实现与演进。

当修改以下目录或文件时，应优先遵守本文件：

- `app/v2/runtime.py`
- `app/v2/registry.py`
- `app/v2/factory.py`
- `app/v2/context.py`
- `app/v2/workspace.py`
- `app/v2/memory.py`
- `app/v2/plan_policy.py`
- `app/v2/replay.py`
- `app/v2/repository.py`
- `app/v2/viewer.py`
- `app/v2/agent_impls/*`

如果与仓库根目录 `AGENTS.md` 存在交叉：

- 根目录 `AGENTS.md` 负责仓库级原则
- 本文件负责 `v2` 目录级细化约束

---

## v2 定位

`v2` 是一个 **中心化多 Agent 编排版 CodeAgent**，服务于高级课程。

它不是对 `v1` 的直接覆盖，也不是把 `v1` 持续堆复杂，而是站在 `v1` 的工程基础之上，演进出新的系统能力，包括：

- Orchestrator + Specialist Agents
- 结构化任务委派（Delegation）
- 共享工作区（Shared Workspace）
- 多 Agent 协作编程
- RePlan / Retry / Fallback
- 更完整的上下文治理
- 更细粒度的 Trace 与执行记录

`v2` 当前聚焦于：

- 中心化调度
- 可控协作
- 可追踪执行
- 结构化多角色分工

`v2` 当前不包含：

- 并行执行
- 自治触发
- 自由对话式 Agent 群聊
- 去中心化协作
- 复杂事件驱动编排

这些能力如果未来需要，应优先放入 `v3` 或后续版本，而不是反向污染 `v2` 的第一阶段实现。

---

## 当前目标

`v2` 当前阶段的核心目标包括：

- 设计并实现多 Agent 数据协议
- 引入 Agent Registry
- 实现 Orchestrator 调度主流程
- 实现 Planner / Analyst / Coder / Tester 等角色分工
- 引入 Shared Workspace
- 支持委派、回流、重试、RePlan
- 提升执行过程的可观测性和可解释性

`v2` 应作为独立实现演进，不应直接破坏 `v1` 的稳定性与课程边界。

---

## 核心设计原则

### 1. `v2` 必须保持中心化、可控、可收敛

`v2` 的首要目标不是“更聪明”，而是：

- 可控协作
- 结构化委派
- 明确职责边界
- 可追踪
- 可失败回流
- 可调试

因此 `v2` 的第一阶段应坚持：

- 只有 Orchestrator 可以统一调度
- 子 Agent 不得自由互聊
- 子 Agent 不得随意自行派生新任务
- 所有关键执行都必须进入 Trace
- 所有失败路径都必须可收敛

---

### 2. Agent 必须是受控执行单元

`v2` 中的子 Agent 不直接拥有无边界外部动作权限。

外部能力应通过受控工具、共享工作区、或复用稳定执行单元完成。

Orchestrator 负责：

- 生成或接收计划
- 选择目标 Agent
- 协调委派
- 处理失败回流
- 决定 replan / fallback / finish

不要把 Orchestrator 退化成“只是转发消息”的薄壳，也不要把子 Agent 变成自由协作网络。

---

### 3. Contract 优先

`v2` 应优先使用结构化对象，例如：

- `AgentSpec`
- `AgentTask`
- `AgentResult`
- `DelegationRecord`
- `SharedWorkspace`
- `ExecutionNode`
- `Plan`
- `PlanStep`

严禁在核心模块边界长期传递裸字典。

---

### 4. 共享工作区与私有上下文必须分层

`v2` 的上下文治理应坚持：

- 公共事实进入 shared workspace
- 角色特定上下文按需裁剪
- 避免所有 Agent 共享全量历史
- 避免把私有推理状态无约束泄漏给所有角色

---

### 5. 优先支持小范围、可验证的多 Agent 编程任务

`v2` 当前适合：

- 结构化项目分析
- 小范围代码修复
- coding + testing + review 闭环
- 基于失败结果的有限回流与重试

`v2` 当前不追求：

- 无边界项目重构
- 自主无限拆任务
- 自由多 Agent 群聊

---

### 6. 可观测性必须覆盖调度链路

`v2` 除共享 Trace 事件外，还应逐步补充：

- `agent_selected`
- `delegation_started`
- `delegation_finished`
- `workspace_updated`
- `replan_started`
- `replan_finished`
- `fallback_triggered`

Trace 必须可以通过 `run_id` 查询。

---

## 模块职责

### `app/v2/runtime.py`

负责：

- Orchestrator 运行主流程
- 按步骤委派 Agent
- 处理回流、重试、replan 与收敛

---

### `app/v2/agent_impls`

负责：

- 各角色 Agent 实现
- Orchestrator / Planner / Analyst / Coder / Tester / Reviewer 角色分工
- 与 payload / llm utils / workspace diff 相关的角色支撑逻辑

应保持角色职责清晰，不要让多个 Agent 大量重叠。

---

### `app/v2/registry.py` 与 `app/v2/factory.py`

负责：

- Agent Registry
- 默认 Agent 装配
- 角色可用性配置

---

### `app/v2/workspace.py`

负责：

- Shared Workspace 读写
- 共享事实沉淀
- artifacts / notes / patch / test 等公共结果收敛

---

### `app/v2/context.py` 与 `app/v2/memory.py`

负责：

- 按角色裁剪上下文
- 管理私有记忆或辅助上下文

---

### `app/v2/replay.py`、`app/v2/repository.py`、`app/v2/viewer.py`

负责：

- 执行记录存取
- replay 支持
- 结果查看与解释辅助

---

## 编码规范

- 所有代码必须带类型标注
- 核心结构优先使用 Pydantic
- Agent 输出必须结构化
- 失败必须可收敛为可解释结果
- 角色边界必须清晰
- 与 `v1` 的复用应显式、可解释

新增模块时，优先判断它属于：

- orchestrator runtime
- agent implementation
- workspace / context / memory
- replay / repository / viewer
- registry / factory / policy

不要为了临时方便把 `v2` 写成混杂的大文件系统。

---

## 安全边界

`v2` 中高风险行为还必须考虑：

- 哪个 Agent 有权限执行
- 是否允许由 Orchestrator 委派
- 是否需要额外 guardrail

不要让子 Agent 获得无边界调度权或无审计副作用。

---

## 演进原则

- `v2` 优先承载中心化多 Agent 协作能力
- 不要把 `v2` 改造成去中心化协作系统
- 并行、自治、自由对话等高级能力不应提前塞入 `v2` 第一阶段
- 共享能力成熟后，再考虑上提到共享层
- 不要让 `v3` 的实验性需求反向污染 `v2`
