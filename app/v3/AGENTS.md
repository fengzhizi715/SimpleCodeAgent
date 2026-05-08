# AGENTS.md

## 适用范围

本文件用于约束 `app/v3` 目录下的设计、实现与演进。

当修改以下目录时，应优先遵守本文件：

- `app/v3/contracts`
- `app/v3/runtime`
- `app/v3/graph`
- `app/v3/skills`
- `app/v3/events`
- `app/v3/trigger`
- `app/v3/adapters`
- `app/v3/runner.py`

如果与仓库根目录 `AGENTS.md` 存在交叉：

- 根目录 `AGENTS.md` 负责仓库级原则
- 本文件负责 `v3` 目录级细化约束

---

## v3 定位

`v3` 是一个 **Graph + Skill + Trigger 驱动的结构化运行时**。

它的目标不是简单地“再增加几个 Agent”，而是把系统演进到新的抽象层，重点验证：

- Task Graph
- Skill Registry
- Execution Kernel
- Event Bus / Event Store
- Trigger Engine
- Graph Validation
- 基于结构化节点的执行报告与恢复语义

`v3` 当前定位为：

- 结构化执行内核实验场
- Skill 驱动的运行时骨架
- 面向后续可扩展自动化能力的受控演进版本

`v3` 当前适合承载：

- repo-aware planning
- graph-based task execution
- coding / testing skill 编排
- planner 生成的恢复模板
- event-triggered fix / re-test 流程
- 更细粒度的 execution report、virtual execution node 与事件记录

`v3` 当前不应被描述为：

- 已完成的通用自治 Agent 平台
- 无限并行的工作流引擎
- 去中心化自组织 Agent 网络
- 无边界事件自动化系统

当前默认内建能力以最小闭环为主：

- `planning`
- `analyze_repo`
- `coding`
- `test_runner`
- `tdd`

其中：

- `coding` 默认通过 `v2_agent_adapter` 复用真实 coder
- `test_runner` 默认通过 `v1_tool_adapter` 复用 shell/test 能力
- `tdd` 是受控的 fix -> re-test 组合 skill，不是自治系统

---

## 当前目标

`v3` 当前阶段的核心目标包括：

- 设计并实现 V3 数据协议
- 引入 TaskGraph / TaskNode / ExecutionReport
- 引入 Skill Registry 与 Skill Executor
- 实现 Graph Executor 与 Execution Kernel
- 引入 Event Bus / Event Store
- 支持 Trigger Rule 与 Trigger Engine
- 通过 adapter 复用稳定的 `v1` / `v2` 执行能力
- 提升 graph execution、event flow 与 trigger chain 的可观测性
- 支持 graph 节点失败后由 trigger 虚拟节点完成恢复，并在最终 report 中收敛状态

`v3` 当前应作为独立实现演进，不应直接破坏 `v1` / `v2` 的稳定性与课程边界。

---

## 核心设计原则

### 1. Skill 必须是受控执行单元

在 `v3` 中：

- Skill 是执行单元
- Tool Skill 通过受控 adapter 访问外部能力
- Composite Skill 负责组织执行，不应内嵌无边界副作用
- `tdd` 这类组合 skill 只能做小规模、可解释的受控循环

Execution Kernel、Graph Executor、Skill Executor 负责：

- 校验 graph
- 调度 skill 执行
- 管理 execution context
- 发布事件
- 收敛执行结果

不得把文件操作、shell 执行等外部行为直接写进 Runtime、Skill 或 Trigger 主逻辑中。

---

### 2. Contract 优先

`v3` 内部核心数据结构应优先定义在 `app/v3/contracts` 中，并保持结构化、可校验。

优先使用的对象包括：

- `TaskGraph`
- `TaskNode`
- `SkillSpec`
- `SkillInput`
- `SkillOutput`
- `TriggerRule`
- `V3Event`
- `ExecutionReport`
- `ExecutionNode`

严禁在核心模块边界长期传递裸字典。

如果当前实现需要临时使用字典：

- 应尽量局限在边界层
- 应尽快收敛回结构化对象

---

### 3. Graph 必须先校验再执行

所有 graph 执行都应遵守：

- 先校验
- 后执行
- 再产出结构化报告

至少应保证：

- 节点 id 唯一
- 依赖关系有效
- 不允许环
- 执行顺序可解释

不要为了快速实验绕过 `GraphValidator`。

---

### 4. Trigger 必须显式注册、显式映射、显式可关

Trigger 是 `v3` 的重要能力，也是最容易失控的部分。

因此必须坚持：

- Trigger Rule 必须显式注册
- 输入映射必须显式声明
- Trigger 执行必须可追踪
- Trigger 应支持禁用
- 不允许隐式扩散式自动触发

允许 planner 在特定场景下生成默认 Trigger 模板，例如：

- `test_failed -> coding`
- `test_failed -> tdd`

但必须保持：

- planner 只生成有限模板，不做自由 trigger 编排
- 显式传入的 `trigger_rules` 优先于 planner 模板
- Trigger 结果必须进入 execution report
- 不允许通过 trigger 在运行时动态改写原始 graph

不要把“未来可能有用的自动化链路”提前塞进默认执行路径。

---

### 5. 对旧版本的复用必须经过 adapter

`v3` 可以复用旧版本的成熟能力，但必须通过 adapter 层完成。

当前边界应保持为：

- `v1 tool` 通过 `v1_tool_adapter` 暴露给 `v3`
- `v2 agent` 通过 `v2_agent_adapter` 暴露给 `v3`

不要在 `v3` 中直接耦合 `v1` / `v2` 的内部流程细节。

目标是：

- 复用稳定能力
- 保持运行时边界清晰
- 避免把 `v3` 退化成旧实现的拼装层

---

### 6. 优先支持小规模、可验证的 graph 编排

`v3` 当前适合：

- 小规模 task graph
- repo-aware planning
- coding + testing 的受控串联
- test failure 后的有限触发式修复

`v3` 当前不追求：

- 无限扩张 graph
- 任意递归触发
- 全自动软件工程系统
- 无边界自治执行

---

### 7. 可观测性是核心能力

`v3` 至少应覆盖或映射以下事件：

- `graph_started`
- `graph_finished`
- `skill_started`
- `skill_finished`
- `skill_failed`
- `test_failed`
- `code_updated`

所有关键执行链路都应尽量满足：

- 可通过 `run_id` 查询
- 可解释
- 可定位失败点

当前阶段优先保证 trace 可查、timeline 可读、恢复链路可解释。
不要把“完整 replay 引擎”写成已完成能力。

如果新增关键流程，应同步补充 trace / event 记录。

---

## 模块职责

### `app/v3/contracts`

负责：

- graph / skill / event / trigger / execution 协议定义
- V3 结构化对象校验
- 图执行和触发链路的数据边界约束

不得掺入运行时业务逻辑。

---

### `app/v3/skills`

负责：

- Skill 抽象
- Skill Registry
- Builtin Skill 实现
- Agent Skill / Tool Skill 适配

Skill 应具备：

- 输入输出结构化
- 能力边界清晰
- 尽量避免隐式副作用
- 对恢复型 Skill，优先把策略收敛在 Skill 内，而不是把 TriggerRule 做复杂

---

### `app/v3/runtime`

负责：

- Execution Kernel
- Graph Executor
- Skill Executor
- Execution Context
- 节点执行收敛、恢复状态判定与报告生成

不得把具体业务策略散落到多个 runtime 文件中。

---

### `app/v3/graph`

负责：

- TaskGraph 构建
- Graph 校验
- 节点依赖关系表达

图构建逻辑与图校验逻辑应尽量分离。
当前 graph 只表达主执行链，trigger 后续动作通过 virtual execution node 进入 report，而不是回写 graph 结构。

---

### `app/v3/events`

负责：

- Event Bus
- Event Store
- 事件发布与订阅基础机制

事件层应尽量通用，不要掺入具体业务分支判断。

---

### `app/v3/trigger`

负责：

- Trigger Rule 注册
- Trigger Engine 执行
- 事件到 Skill 输入的映射

Trigger 必须保持：

- 显式注册
- 可调试
- 可关闭
- 可追踪

当前 Trigger 只负责：

- 事件匹配
- payload 映射
- 触发 Skill
- 记录 virtual execution node

不要在 Trigger 层堆叠复杂条件、预算控制或多级自治链。

---

### `app/v3/adapters`

负责：

- 复用稳定版本能力的桥接层
- `v1 tool` 到 `v3 skill` 的适配
- `v2 agent` 到 `v3 skill` 的适配

适配层用于解耦，不应把 `v3` 退化成对旧版本内部实现的直接拼接。

---

## 编码规范

- 所有代码必须带类型标注
- 核心结构优先使用 Pydantic
- 优先让每个 Skill / Trigger / Graph 组件职责单一
- 避免隐式共享状态
- 返回结果必须结构化
- 失败必须可收敛为可解释结果
- 对 `v1` / `v2` 的依赖应优先收敛在 adapter 层

新增模块时，优先判断它属于：

- `contracts`
- `runtime`
- `graph`
- `skills`
- `events`
- `trigger`
- `adapters`

不要为了临时方便把边界打穿。

当前目录边界也应与现状保持一致：

- `app/v3` 保留内核目录：`contracts / skills / graph / runtime / events / trigger / adapters`
- `app/v3/runner.py` 作为共享 API / CLI 的装配入口
- HTTP 路由走共享 `app/api`
- CLI 入口走共享 `app/cli` 或主入口
- trace 存储与 viewer 优先复用共享 `app/trace`，`app/v3/trace` 只保留薄 helper

---

## 安全边界

`v3` 中的 Skill 或 Trigger 默认不得：

- 删除任意文件
- 执行无限制 shell 命令
- 自动安装依赖
- 自动发起任意网络请求
- 自动执行 git 高风险操作

所有高风险行为必须考虑：

- 哪个 Skill 可以触发
- Trigger 是否允许自动触发该动作
- Event chain 是否会导致副作用扩散
- 是否可以通过 trace / event 审计

---

## 演进原则

- `v3` 优先承载 Graph / Skill / Trigger 结构化运行时能力
- 不要把 `v3` 做成“更复杂的 v2”
- 不要为了未来过度抽象
- 无边界事件自动化和无限扩张图执行不应提前塞入当前阶段
- 不要把 planner 模板演进成动态 graph 改写器
- 共享能力成熟后，再考虑上提到共享层
- 不要让 `v3` 的实验性需求反向污染 `v1` / `v2`
