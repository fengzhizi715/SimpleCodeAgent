# V2 当前状态与待办清单

本文档用于记录 `SimpleCodeAgent V2` 相对于目标设计的当前实现状态，帮助后续开发、课程演示与版本规划保持一致。

当前判断基于以下目标边界：

- 版本名称：`SimpleCodeAgent V2 — Centralized Multi-Agent Orchestration`
- 版本目标：在 `v1` 单智能体基础上，构建一个
  - 中心化调度
  - 多角色分工
  - 可共享上下文
  - 可失败回流
  - 可追踪执行链路
  的多智能体系统

---

## 1. 当前结论

`v2` 目前已经不是空目录，而是一个 **可运行的 MVP 骨架**，但距离“功能完成的 V2”还有明显差距。

更准确地说：

- 已经完成：
  - 多 Agent 基础协议
  - Registry / Workspace / Context Builder 基础版
  - Agent 实现已拆分到 `app/v2/agent_impls/*`，职责边界更清晰
  - `Planner / Analyst / Coder / Tester` 四个角色的 P0 能力
  - `ReviewerAgent` 基础版
  - 中心化 `Orchestrator Runtime`
  - 一次 `Tester -> Coder` 失败回流
  - 基础 trace 事件
  - API 入口接入
  - CLI `v2` 入口接入
- 还没有完成：
  - 真正完整的 execution log / replay
  - workspace 持久化与 artifact 治理增强版
  - 更完整的 CLI/demo 闭环

因此，当前 `v2` 应被视为：

- **已起好工程骨架**
- **可以继续演进**
- **还不应宣称“V2 已完成”**

### 1.1 当前边界与已知限制

当前 `v2` 已具备多 Agent 主链路，但仍有几条边界需要在文档与教学中明确说明：

1. `Agent Registry` 目前仍是静态装配，而不是动态服务发现。
   - 当前由 `app/v2/factory.py` 负责注册默认 Agent，属于“可插拔的默认装配层”。
   - 这符合当前阶段聚焦“中心化、可控、可教学”的目标。
   - 但它还不是插件市场式、动态发现式的 registry。

2. “子 Agent 不允许再委派”现在已经收紧为更强的类型边界。
   - 子 Agent 拿到的是不包含委派能力的 `AgentContext`。
   - 调度能力被拆到只供 orchestrator 持有的 `OrchestratorDelegationClient` 中。
   - 这让“只有 orchestrator 可统一调度”不再只是运行时拦截，而是从接口层就区分了调度端与执行端。
   - 当前剩余的增强空间主要是更细粒度的能力权限模型，而不是是否允许子 Agent 再委派。

3. `Trace / Execution Log` 已进入可回放阶段，但完备性仍应按 MVP 口径宣传。
   - 协议层已经支持 `started_at / ended_at / parent_event_id` 等更完整字段。
   - 当前运行时也开始补齐这些字段并形成 replay 视图。
   - 但它更适合被描述为“基础版 execution log / replay”，而不是已经完成的全量可观测系统。

4. `CoderAgent` 复用 `v1 AgentLoop`，需要明确解释为“嵌套执行单元”，而不是第二个 orchestrator。
   - 这样做的目的是复用 `v1` 已验证过的单 Agent coding executor，降低 `v2` MVP 的实现成本。
   - 它会带来两层 loop 的教学语义，因此必须明确边界：
   - `v2 Orchestrator` 负责多 Agent 编排。
   - `CoderAgent` 内部的 `v1 AgentLoop` 只负责单任务执行，不具备再次调度其他 Agent 的权力。

5. `app/v2/agent_impls/common.py` 目前是兼容层（re-export），用于平滑拆分后的导入迁移。
   - 新代码应优先直接从 `payloads.py / llm_utils.py / workspace_diff.py` 导入。
   - 当仓库内不再有对 `common.py` 的直接引用后，可在后续版本移除该兼容层。

---

## 2. 已完成项

### 2.1 基础协议

已完成的核心协议包括：

- `AgentSpec`
- `AgentTask`
- `AgentResult`
- `DelegationRecord`
- `SharedWorkspace`
- `TestReport`
- `Plan`
- `PlanStep`

对应文件：

- `app/contracts/agent.py`
- `app/contracts/planner.py`

### 2.2 Agent Registry

已支持：

- 注册 Agent
- 按 `agent_id` 获取 Agent
- 列出全部 Agent spec
- 列出当前可用 Agent
- 默认装配支持 `enable_reviewer` 开关
- 提供教学/调试角色矩阵输出（`describe_agent_matrix` + CLI debug 命令）

对应文件：

- `app/v2/registry.py`
- `app/v2/factory.py`
- `app/v2/agent_impls/__init__.py`

### 2.3 Shared Workspace

当前已支持的共享字段包括：

- `user_goal`
- `current_plan`
- `project_summary`
- `latest_patch_summary`
- `latest_test_result`
- `artifacts_index`
- `execution_notes`
- `private_context`

已支持的基本操作包括：

- 更新 plan
- 更新项目摘要
- 更新 patch 摘要
- 更新测试结果
- 追加执行备注
- 更新私有上下文
- 记录 artifact index

对应文件：

- `app/v2/workspace.py`

### 2.4 Context Builder

当前已支持按角色裁剪上下文：

- `planner`
- `analyst`
- `coder`
- `tester`

当前实现已经避免了“所有 Agent 共享全量上下文”的问题，但裁剪策略仍然是基础版。

对应文件：

- `app/v2/context.py`

### 2.5 核心角色 MVP

#### Planner Agent

已支持：

- 生成初始计划
- 根据失败重新生成计划
- 为步骤补齐 `goal / type / suggested_agent / input_requirements / success_criteria`

当前实现已优先尝试使用 LLM 输出结构化计划；当结构化解析失败时，才回退到 `v1 SimplePlanner`。

#### Analyst Agent

已支持：

- 列目录
- 搜索关键代码线索
- 读取关键文件片段
- 输出结构化项目分析
- 写入 workspace

#### Coder Agent

已支持：

- 读取 workspace 中的项目摘要与测试反馈
- 复用 `v1 AgentLoop`
- 输出 patch summary
- 输出修改文件列表、diff 预览与风险提示

#### Tester Agent

已支持：

- 执行 shell 验证命令
- 基于改动文件选择更聚焦的测试命令
- 输出结构化测试报告
- 在失败时给出 `suggested_next_action`

对应文件：

- `app/v2/agent_impls/planner.py`
- `app/v2/agent_impls/analyst.py`
- `app/v2/agent_impls/coder.py`
- `app/v2/agent_impls/tester.py`
- `app/v2/agent_impls/reviewer.py`

#### Reviewer Agent

已支持：

- Review 最新 patch 结果
- 输出结构化 issues 列表
- 规则库 review
- 可选的 LLM 结构化 review
- 规则与 LLM review 结果合并
- 将 review 结果写入 workspace / artifact / replay

当前实现为“规则库 + 可选 LLM review”的基础版 reviewer，重点用于补齐工程闭环并提升 review 上限。

### 2.6 Orchestrator Runtime

当前主流程已具备：

1. 接收用户任务
2. 调用 planner 生成 plan
3. 按步骤委派到不同 Agent
4. 更新 shared workspace
5. 处理失败、回流、replan
6. 输出最终答案

已支持：

- `max_steps`
- 有限 `replan`
- 一次 `Tester -> Coder` 回流
- fail fast
- final answer 汇总

对应文件：

- `app/v2/runtime.py`

### 2.7 Trace 基础事件

当前已覆盖的多 Agent trace 事件包括：

- `run_started`
- `run_finished`
- `run_failed`
- `agent_selected`
- `delegation_started`
- `delegation_finished`
- `workspace_updated`
- `replan_started`
- `replan_finished`

当前还已支持：

- 结构化 trace 字段落库
- 按 `run_id / root_run_id / session_id` 查询时间线
- execution log 基础视图
- delegation tree 基础视图
- execution node 基础视图

对应文件：

- `app/contracts/trace.py`
- `app/trace/events.py`
- `app/v2/runtime.py`
- `app/trace/repository.py`
- `app/v2/replay.py`
- `app/v2/viewer.py`

### 2.8 API 入口

当前 API 已可选择：

- `version="v1"`
- `version="v2"`

其中 `v2` 已接入 `OrchestratorRuntime`。

对应文件：

- `app/api/routes/agent.py`
- `app/api/deps.py`

### 2.9 Workspace / Delegation 持久化与 Replay 基础版

当前已支持：

- `SharedWorkspace` 落库
- `DelegationRecord` 落库
- `runs` 元数据与 `workspace / delegation / trace` 关联
- 按 `run` 回放主要执行数据
- 按 `session` 聚合回放主要执行数据
- 教学展示友好的 `teaching_view`
- Debug API 的 replay 输出
- artifact 内容持久化与回放
- execution node 基础视图

对应文件：

- `app/v2/repository.py`
- `app/v2/runtime.py`
- `app/api/routes/debug.py`

---

## 3. 部分完成项

下面这些能力已经有雏形，但距离“满足设计目标”还有差距。

### 3.1 Orchestrator Agent 本体

当前状态：

- 已有 `OrchestratorRuntime`
- 但没有独立的 `OrchestratorAgent` 类

影响：

- 目前“调度逻辑”和“Agent 身份”仍然混在 runtime 中
- 不利于后续引入更完整的 orchestrator prompt、策略和 trace 视角

### 3.2 Planner Agent

当前状态：

- 已能优先通过 LLM 生成结构化 plan
- 结构化解析失败时会回退到 `v1 SimplePlanner`

缺口：

- replan 还不够智能
- 步骤级策略解释能力还偏弱

### 3.3 Analyst Agent

当前状态：

- 已能输出项目摘要、模块职责、入口文件、关键文件和编码提示

缺口：

- 还没有更深的模块依赖分析
- 还缺少更细粒度的文件级上下文选择策略

### 3.4 Coder Agent

当前状态：

- 已能借助 `v1 AgentLoop` 做实际修改
- 已输出文件变更、diff 预览和风险说明

缺口：

- diff / patch 仍是轻量预览版
- patch artifact 版本治理仍然较弱

### 3.5 Tester Agent

当前状态：

- 已能跑命令并输出结构化测试报告
- 已会优先选择更聚焦的测试命令

缺口：

- 构建校验与测试范围控制仍然有限
- 失败原因分类还比较粗糙

### 3.6 Retry / RePlan / Fallback

当前状态：

- 已支持单次失败回流
- 已支持有限 replan

缺口：

- 触发条件还不够精细
- retry 策略还不够清楚
- fallback 类型还很少

### 3.7 Trace / Observability

当前状态：

- 事件类型和内存态 trace 已有

缺口：

- execution log 还不够完整
- session replay 还没成型
- 控制台链路展示还没做成正式体验

---

## 4. 未完成项

### 4.1 Reviewer Agent

当前已实现基础版。

还没有：

- 更强的规则库覆盖
- 更丰富的 LLM review 策略
- 与测试失败结果的联动复核
- 更细粒度的 review 策略配置

### 4.2 CLI 的 v2 入口

当前已支持 `CLI -> v2 runtime`。

并已提供基础教学调试命令：

- `python scripts/run_cli.py debug agent-matrix`

但仍然还没有形成真正稳定的课程 Demo 闭环，例如：

- 适合演示的固定任务脚本
- 更友好的执行链路展示
- 面向课堂的预置工作区和输出模板

### 4.3 Workspace 持久化的增强版

当前已支持 workspace 快照落库与按 `run / session` 查询。

还没有：

- 跨 run 的增量恢复策略
- workspace 历史版本管理
- 更完整的状态迁移与恢复策略

### 4.4 Artifact 管理系统

当前已支持：

- artifact 内容落库
- artifact 按 run/session 回放
- artifact 版本基础字段

还没有：

- 更强的 artifact repository 抽象
- artifact 版本治理策略
- 更丰富的 artifact 检索与筛选
- artifact 之间的依赖关系表达

### 4.5 更强的 capability-based 路由

当前 registry 主要按 `agent_id` 获取。

还没有：

- 按 capability 查询
- 按任务类型自动选 Agent
- 启用/禁用的管理接口

### 4.6 Trace 落库的增强版

当前已支持：

- 结构化 trace 字段落库与查询
- execution log 基础视图
- delegation tree 基础视图
- debug replay 输出

还没有：

- 更完整的 execution node 模型
- 更细粒度的 UI 查询接口
- 更强的 trace 聚合筛选能力

### 4.7 Parent-child relation 的增强版执行树

当前已具备：

- `root_run_id`
- `parent_run_id`
- `parent_event_id`
- delegation 记录与 run/session 级回放
- delegation tree 基础展示
- execution node 基础视图

还没有：

- 更复杂的树形聚合与折叠视图
- 更强的 execution node 关系建模

### 4.8 Session 回放的增强版

当前已支持 session 级聚合回放。

还没有：

- 更丰富的时间线筛选能力
- 多次 delegation 链路图的增强版
- 更丰富的课堂/前端展示模板

### 4.9 V2 专属 Memory 体系

当前只有：

- shared workspace
- `private_context` 雏形

还没有：

- shared/private memory 的正式抽象
- memory 策略
- 上下文裁剪与记忆治理的系统化实现

### 4.10 V2 Demo 闭环

当前已具备基础演示入口，但还没有形成稳定的完整闭环：

- CLI demo（基础可用）
- 教学 demo
- 从用户任务到多 Agent trace 展示的完整演示路径

---

## 5. 对照最初目标后的判断

如果按“是否已经达到 V2 设计要求”来评估，当前更合理的结论是：

- `v2` 的 **工程骨架已完成**
- `v2 MVP` 的 **主链路已打通**
- `v2` 的 **关键能力还没有全部完成**

也就是说，当前阶段最适合的表述不是：

- “V2 已完成”

而是：

- “V2 MVP 骨架已完成，可继续进入功能强化阶段”

---

## 6. 建议的下一阶段优先级

### P0：当前已完成

- `PlannerAgent` 已升级为优先使用结构化 LLM planner，并保留回退策略
- `AnalystAgent` 已补齐结构化项目分析输出
- `CoderAgent` 已补齐文件列表 / diff 预览 / 风险摘要
- `TesterAgent` 已增强命令选择与失败分类
- CLI 已接入 `v2` 入口
- Agent 已拆分到 `agent_impls/*` 并补齐基础 happy path 测试
- CLI 已支持 `debug agent-matrix` 展示角色矩阵

### P1：已启动并完成基础版

已完成：

- trace 落库结构升级
- 支持按 `session / run` 回放主要过程
- `workspace` 可持久化
- delegation 可持久化

后续仍需继续：

- 更清晰的 delegation tree 增强版
- 更面向课程和 UI 的 replay 增强版

### P2：进入增强版

当前已完成基础版：

- `ReviewerAgent`
- artifact 管理增强版（基础落库与回放）
- execution node 基础视图

后续仍可继续：

- 升级 memory 策略
- 继续增强 reviewer 的智能性
- 为未来并行执行和 `v3` 事件驱动保留扩展点

---

## 7. 一句话总结

当前 `v2` 已经具备“中心化多 Agent 编排”的雏形和主链路，但还没有达到最初目标中的完整工程化实现。下一阶段的重点不再是“从零搭骨架”，而是把规划、分析、编码、测试、trace 和 workspace 这些关键环节做扎实。
