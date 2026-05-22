# Agent Runtime

本文档说明 `SimpleCodeAgent` 当前三条运行时主线：

- `v1`：单 Agent、工具驱动、稳定可演示
- `v2`：中心化多 Agent 编排（MVP）
- `v3`：`Graph + Skill + Trigger` 驱动的结构化 Runtime

目标是帮助你快速理解“谁负责调度、谁负责执行、如何收敛失败、如何追踪执行链路”。

---

## 1. 统一运行时约束（v1 / v2 / v3 共用）

- Agent 不直接执行外部动作；所有文件、Shell、检索行为都经由 Tool。
- Runtime 负责循环控制、状态管理、失败收敛和 trace 记录。
- 跨模块数据交换优先使用结构化 contract（Pydantic 模型）。
- 高风险行为必须可审计、可追踪，不依赖隐式副作用。

对 `v3` 还需要额外强调：

- graph 必须先校验再执行
- trigger 必须显式注册、显式映射、显式可关
- governance 必须先于 autonomy

---

## 2. v1 Runtime（单 Agent）

`v1` 是当前教学主线，强调“可预测、可调试、可验证”。

### 2.1 架构图（组件与数据流）

下图概括 **v1 Agent Runtime** 的职责拆分：编排只在 `AgentLoop`；外部动作只经由 **Tool**；LLM 调用隔离在 **RuntimeExecutor**；观测与会话落在共享底座。

```mermaid
flowchart TB
  subgraph Entry["调用入口"]
    CLI["CLI / scripts"]
    API["FastAPI · version=v1"]
  end

  subgraph RuntimePkg["app/v1/runtime"]
    AL["AgentLoop · loop.py"]
    RUN["run() · 主循环"]
    RWP["run_with_plan()"]
    PE["PlanExecutor · plan_executor.py"]
    DTE["DirectToolExecutor · direct_tool_executor.py"]
    RE["RuntimeExecutor · executor.py"]
    RC["RunContext · context.py"]
    ST["AgentState · state.py"]
  end

  subgraph SharedLLM["app/llm"]
    Prov["LLMProvider.chat()"]
  end

  subgraph Tools["app/v1/tools · 唯一外部动作入口"]
    REG["ToolRegistry"]
    RTR["ToolRouter"]
    TImpl["ReadFile / ShellRun / WriteFile / RAG ..."]
  end

  subgraph Observability["Memory & Trace"]
    MEM["SessionMemory / SummaryMemory · app/v1/memory"]
    TR["SQLiteTraceRepository + JsonlTraceRecorder · app/trace"]
    DB["SQLite · app/db"]
  end

  CLI --> AL
  API --> AL
  AL --> RUN
  AL --> RWP

  RWP --> PE
  PE --> DTE
  PE -->|"每步子任务再次调用"| RUN

  RUN --- RC
  RUN --- ST
  RUN --> RE
  RE --> Prov

  RUN -->|"解析 tool_calls"| REG
  DTE --> REG
  REG --> RTR --> TImpl

  RUN --> MEM
  RUN --> TR
  MEM --> DB
  TR --> DB
```

同一次 API / CLI 调用只会进入 **`run()`** 与 **`run_with_plan()`** 二者之一；上图把两条路径画在同一图中便于对照。

**读图要点**

| 模块 | 职责 |
|------|------|
| `AgentLoop` | `max_steps` / 超时、`RunResult` 组装、trace 事件、fallback 收敛 |
| `RuntimeExecutor` | 组装 `RunRequest`，调用 `LLMProvider`，捕获异常并返回同构 fallback |
| `PlanExecutor` | 复杂任务：顺序执行 `PlanStep`，可跳过 LLM 直接写文件、汇总失败语义 |
| `DirectToolExecutor` | 规划路径上的确定性工具执行与校验 |
| `ToolRegistry` / `ToolRouter` | 路由模型 tool call；异常转为 `ToolResult(is_error=true)`，不炸主循环 |
| `RunContext` / `AgentState` | 单次 run 的配置快照与可变对话/计数状态 |

### 2.2 主流程

1. 读取历史会话消息，组装本轮上下文。
2. 进入 step 循环（受 `max_steps` 和超时限制）。
3. 调用模型并解析响应：
   - 有 `tool_calls`：执行工具，回填工具结果，进入下一轮。
   - 有最终文本：结束并返回结果。
   - 空结果/异常：进入 fallback。
4. 持久化 session 消息、run 元数据和 trace。

### 2.3 失败收敛

- 超时：停止运行并返回失败结果。
- 达到最大步数：主动停止，避免死循环。
- 工具失败：以结构化 `ToolResult(is_error=true)` 回填给模型或上层处理。
- 模型异常：构造同构 fallback 结果，保证上层可消费。

### 2.4 关键实现位置

- 主循环：`app/v1/runtime/loop.py`
- 单步执行：`app/v1/runtime/executor.py`
- 规划执行：`app/v1/runtime/plan_executor.py`
- 工具注册与路由：`app/v1/tools/registry.py`、`app/v1/tools/router.py`

---

## 3. v2 Runtime（中心化多 Agent，MVP）

`v2` 采用中心化 orchestrator，不做去中心化自治调度。

### 3.1 角色分工

- `OrchestratorRuntime`：主流程调度与收敛控制
- `PlannerAgent`：生成/重生结构化计划
- `AnalystAgent`：项目分析与上下文摘要
- `CoderAgent`：局部编码修改（内部复用 v1 `AgentLoop` 作为执行单元）
- `TesterAgent`：命令执行与测试报告
- `ReviewerAgent`：可选审查环节（MVP 可开关）

### 3.2 主流程

1. 接收任务，初始化 `SharedWorkspace`。
2. 委派 `PlannerAgent` 生成结构化计划。
3. 按 step 委派目标 Agent 执行并更新 workspace/artifacts。
4. 根据结果做收敛控制：
   - tester 失败可回流 coder 修复
   - 连续失败触发 replan
   - 达上限 fail-fast/fallback
5. 汇总最终输出并落 trace/replay 数据。

### 3.3 边界

- 仅 orchestrator 持有委派能力（通过专用委派客户端）。
- 子 Agent 仅执行被委派任务，不再递归调度其他子 Agent。
- 当前仍是 MVP：主链路已打通，但并非完整生产级编排系统。

### 3.4 关键实现位置

- 主运行时：`app/v2/runtime.py`
- 上下文裁剪：`app/v2/context.py`
- Agent 注册：`app/v2/registry.py`、`app/v2/factory.py`
- 角色实现：`app/v2/agent_impls/*`
- Workspace 与回放：`app/v2/workspace.py`、`app/v2/repository.py`、`app/v2/replay.py`

---

## 4. v3 Runtime（Graph + Skill + Trigger）

`v3` 的重点不是“再增加几个 Agent”，而是把运行时提升到新的抽象层：

- 先有 `TaskGraph`
- 再由 `Skill` 执行节点
- 再根据 `Event / Trigger / Governance` 决定是否进入 follow-up

### 4.1 角色分工

- `run_v3`
  - 总装配入口，负责把 planning、graph、trigger、governance、trace、audit 串起来
- `PlanningSkill / plan_v3_graph`
  - 负责生成 `TaskGraph` 与默认 trigger 模板
- `GraphValidator`
  - 负责节点、依赖、技能引用和 graph 结构校验
- `GraphExecutor`
  - 负责按照依赖关系推进节点执行
- `SkillExecutor`
  - 负责调用具体 Skill
- `ExecutionKernel`
  - 负责收敛执行上下文、事件结果、trigger diagnostics 和最终 `ExecutionReport`
- `EventBus / EventStore`
  - 负责显式发布和记录 `V3Event`
- `TriggerEngine / TriggerRegistry`
  - 负责匹配事件与 trigger rule
- `TriggerGuard / Governance`
  - 负责 allow / block / cooldown / budget exhausted / propagation limited 的治理判断
- `AutonomyRuntime`
  - 负责受控 follow-up task，而不是无边界自治

### 4.2 主流程

1. 接收任务，准备 `SkillRegistry`、`EventBus`、`EventStore`、Governance 状态。
2. 如果没有显式传入 graph，则先用 `PlanningSkill` 生成 `TaskGraph`。
3. 用 `GraphValidator` 校验 graph；非法 graph 直接失败收敛。
4. `GraphExecutor` 顺序推进可执行节点。
5. `SkillExecutor` 运行节点 Skill，并把结果写回 `ExecutionContext`。
6. 节点执行过程中发布 `V3Event`，由 `TriggerEngine` 判断是否命中 `TriggerRule`。
7. 如果命中 trigger，再由 Governance 判断：
   - `Allowed`
   - `Blocked`
   - `Cooled Down`
   - `Propagation Limited`
   - `Budget Exhausted`
8. 如果允许，再执行 follow-up skill 或受控 autonomy task。
9. `ExecutionKernel` 收敛出 `ExecutionReport`、`TriggerDiagnostic` 和运行时摘要。
10. 持久化 trace、event history、runtime summary、audit 数据。

### 4.3 v3 运行时分层图

```mermaid
flowchart TB
  Entry["CLI / API · version=v3"] --> RV3["run_v3()"]

  subgraph GraphLayer["Graph Layer"]
    PLAN["plan_v3_graph() / PlanningSkill"]
    GV["GraphValidator"]
    TG["TaskGraph"]
  end

  subgraph ExecLayer["Execution Layer"]
    GE["GraphExecutor"]
    SE["SkillExecutor"]
    EK["ExecutionKernel"]
    EC["ExecutionContext"]
    ER["ExecutionReport"]
  end

  subgraph EventLayer["Event / Trigger Layer"]
    EB["EventBus"]
    ES["EventStore"]
    TR["TriggerRegistry"]
    TE["TriggerEngine"]
  end

  subgraph GovLayer["Governance Layer"]
    GUARD["TriggerGuard"]
    BUD["ExecutionBudgetState"]
    COOL["CooldownManager"]
    PROP["PropagationState"]
    AUTO["AutonomyRuntime"]
  end

  subgraph Reuse["Adapters"]
    V1["v1_tool_adapter"]
    V2["v2_agent_adapter"]
  end

  RV3 --> PLAN --> TG --> GV --> GE
  GE --> SE
  GE --> EB --> ES
  EB --> TE --> GUARD
  GUARD --> BUD
  GUARD --> COOL
  GUARD --> PROP
  TE --> AUTO
  SE --> V1
  SE --> V2
  GE --> EK --> EC --> ER
```

### 4.4 失败收敛与恢复语义

`v3` 的失败收敛不只看“这个任务最终成没成功”，还要看：

- 哪个节点失败了
- 是否发出了关键 event
- 是否命中了 trigger
- follow-up 是真的执行了，还是被 governance 拦截
- recovery 是真的补救成功，还是在 `no_code_changes` 之类的 stop reason 处收敛

这也是为什么 `v3` 的结果页里会强调：

- `Runtime Mode`
- `Event -> Trigger -> Follow-up`
- `Recovery Path`
- `Governance Explain`

### 4.5 关键实现位置

- 运行入口：`app/v3/runner.py`
- graph 校验：`app/v3/graph/graph_validator.py`
- 图执行：`app/v3/runtime/graph_executor.py`
- Skill 执行：`app/v3/runtime/skill_executor.py`
- 执行上下文与 report：`app/v3/runtime/execution_context.py`
- 运行时收敛：`app/v3/runtime/execution_kernel.py`
- 事件系统：`app/v3/events/*`
- trigger 系统：`app/v3/trigger/*`
- governance：`app/v3/governance/*`
- 运行时摘要：`app/v3/runtime/runtime_summary.py`

---

## 5. v2 与 v3 的运行时差异

这两个版本都已经不是简单单 Agent，但复杂度来源不同：

| 维度 | v2 | v3 |
| --- | --- | --- |
| 核心抽象 | Orchestrator + Specialist Agents | Task Graph + Skills + Triggers |
| 调度中心 | `OrchestratorRuntime` | `GraphExecutor` + `ExecutionKernel` |
| 执行单元 | Agent | Skill / Graph Node |
| 失败收敛 | replan / 回流 / fail-fast | event / trigger / governance / recovery path |
| 用户感知 | 协作编排 | runtime 推进 |
| 典型页面 | History / Run Detail / Replay | Run Detail / Autonomy / Runtime Status |

可以把两者简单理解成：

- `v2` 在回答“多个角色怎么协作完成任务”
- `v3` 在回答“一个结构化运行时如何推进 graph、处理 event、治理 follow-up”

---

## 6. Runtime 与可观测性

运行时至少应保证：

- 可识别 run/session 维度
- 可追踪关键事件（调用、委派、工具、失败、完成）
- 可重放主要执行过程（尤其是 `v2` 的 delegation 链路和 `v3` 的 event / trigger 链路）

当前建议把 trace 当作“调试与教学的一等产物”，而不是附属日志。

---

## 7. 教学建议

- 先讲 `v1` 的单循环与工具回填，再引入 `v2` 的中心化委派。
- 对比说明：`v2` 的复杂度来自“角色协作编排”，不是“让每个 Agent 更智能”。
- 再继续引入 `v3`，强调复杂度已经从“谁来做”转向“runtime 如何推进、治理和收敛”。
- 演示时优先展示可收敛场景：`plan -> code -> test -> (optional review)`。
- `v3` 演示时优先展示：
  - `测试失败 -> 自动补救 -> 再测`
  - `代码变更 -> 自动 follow-up test`
  - `事件命中但被 governance 拦截`
