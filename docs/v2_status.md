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
  - `Orchestrator / Planner / Analyst / Coder / Tester` 五个角色的 P0 能力
  - `ReviewerAgent` 增强基础版
  - 中心化 `Orchestrator Runtime`
  - 一次 `Tester -> Coder` 失败回流
  - 基础 trace 事件
  - API 入口接入
  - CLI `v2` 入口接入
  - WebUI 基础运行页、历史页、执行回放页
  - 按次运行选择启用的 V2 Agent（Planner 固定启用，Analyst / Coder / Tester / Reviewer 可配置）
  - V2 内部 Coder 子运行不再作为独立 V1 顶层历史展示
- 还没有完成：
  - 真正完整的 execution log / replay 增强版
  - workspace 与 artifact 治理增强版
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
   - 内层 `v1 AgentLoop` 产生的 run 会被标记为 `is_top_level=False`，并以 `parent_run_id` 关联外层 V2 run。
   - 运行历史默认只展示用户发起的顶层 run；历史遗留的 `session_id LIKE '%:v2:coder'` 内部 run 会被回填/过滤，避免误显示为独立 V1 运行。

5. Tester / Reviewer 当前是“可配置参与”的协作角色，而不是每次 V2 运行都强制执行。
   - Orchestrator / Planner 始终启用。
   - Analyst / Coder / Tester / Reviewer 可通过 API/WebUI 的运行级配置启用或禁用。
   - 关闭 Tester 时，V2 可以用于“快速修复 / 只要代码改动”的场景，但最终答复应避免宣称已通过测试。
   - 开启 Tester 时，系统会优先使用项目分析结果选择验证命令，但验证命令策略仍属于基础版。

6. `app/v2/agent_impls/common.py` 目前是兼容层（re-export），用于平滑拆分后的导入迁移。
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

#### Orchestrator Agent

已支持：

- 作为独立 `OrchestratorAgent` 注册进 Agent Registry
- 在 Agent Matrix / `/debug/agents` / WebUI Agents 页中展示调度者身份
- 输出中心化调度策略快照，包括启用 Agent、`max_steps`、`max_replans`、timeout、`review_strategy`
- 输出 orchestrator system prompt，明确中心化委派、子 Agent 不可再委派、retry/replan/fail-fast 边界
- 输出策略 profile（`fast_fix / balanced / quality_gate`），根据启用 Agent 自动选择执行风格
- 输出 plan explanation，解释过滤后的计划为什么符合当前策略
- 输出 delegation explanation，并写入 `agent_selected / delegation_started` trace payload
- 将 orchestrator policy / prompt / strategy profile / plan explanation 写入 workspace 的 `private_context["orchestrator"]`
- 在 `run_started` trace payload 中记录 orchestrator policy 与 strategy profile，便于后续回放和教学解释

当前实现中，`OrchestratorRuntime` 仍负责稳定的执行主循环；`OrchestratorAgent` 承担“身份 + prompt + 策略 profile + 调度解释 + trace 视角”。这避免一次性重写主循环，同时为后续引入 LLM 驱动的 orchestrator decision 留出边界。

对应文件：

- `app/v2/agent_impls/orchestrator.py`
- `app/v2/agent_impls/planner.py`
- `app/v2/agent_impls/analyst.py`
- `app/v2/agent_impls/coder.py`
- `app/v2/agent_impls/tester.py`
- `app/v2/agent_impls/reviewer.py`

#### Reviewer Agent

已支持：

- Review 最新 patch 结果
- 输出结构化 issues 列表
- 增强版规则库 review
- 可配置的 LLM 结构化 review
- 可配置的规则分组（scope / testing / security / maintainability / boundaries / api / domain）
- 规则与 LLM review 结果合并
- 读取 diff previews、改动文件片段和关键文件片段
- 联动最近测试结果进行复核，并支持 `off / suggest / block` 三种测试失败策略
- 基础 review 策略配置（`llm_enabled / strictness / max_issues / focus_areas / rule_groups / test_failure_mode`）
- WebUI `/agents` 页支持点击 Reviewer 配置策略，RunPage 会读取保存后的策略用于新运行
- 将 review 结果写入 workspace / artifact / replay

当前实现为“增强规则库 + 可配置 LLM review”的 reviewer，重点用于补齐工程闭环并提升 review 上限。

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
- `run_timeout_seconds`
- 有限 `replan`
- 一次 `Tester -> Coder` 回流
- fail fast
- final answer 汇总
- 运行级 Agent 启用配置
- 按启用 Agent 过滤 plan step
- Reviewer 只在启用时自动跟随 Coder 执行

当前默认教学链路倾向：

- 修复/实现类任务：`Planner -> Analyst -> Coder -> Tester`
- 快速修复模式：可通过运行配置关闭 `Tester / Reviewer`，形成 `Planner -> Analyst -> Coder`

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

当前 V2 API 还支持：

- `v2_enabled_agents`：按次运行控制启用的 Agent，`orchestrator / planner` 会始终启用
- `run_timeout_seconds`：控制运行超时
- `workdir`：指定目标项目目录

对应文件：

- `app/api/routes/agent.py`
- `app/api/deps.py`

### 2.9 Workspace / Delegation 持久化与 Replay 基础版

当前已支持：

- `SharedWorkspace` 落库
- `DelegationRecord` 落库
- `runs` 元数据与 `workspace / delegation / trace` 关联
- `runs.workdir` 持久化
- `runs.is_top_level / parent_run_id` 用于区分用户顶层运行与内部子运行
- 按 `run` 回放主要执行数据
- 按 `session` 聚合回放主要执行数据
- 教学展示友好的 `teaching_view`
- Debug API 的 replay 输出
- artifact 内容持久化与回放
- execution node 基础视图
- 运行历史默认过滤 V2 Coder 内部复用 V1 loop 产生的非顶层 run

对应文件：

- `app/v2/repository.py`
- `app/v2/runtime.py`
- `app/db/sqlite.py`
- `app/api/routes/debug.py`

### 2.10 WebUI 基础版

当前已支持：

- 新建运行任务
- 选择 `v1 / v2`
- 配置 `workdir / max_steps / run_timeout_seconds`
- V2 运行级 Agent 勾选配置
- 查看运行历史
- 查看 V2 执行回放
- 查看 V2 trace 页面

当前 WebUI 更适合作为教学/调试入口，而不是完整产品化控制台。

对应文件：

- `webui/src/pages/RunPage.vue`
- `webui/src/pages/HistoryPage.vue`
- `webui/src/pages/RunExecutionPage.vue`
- `webui/src/pages/RunTracePage.vue`

---

## 3. 增强中能力

下面这些能力已经超过 MVP 雏形，进入“可运行但仍需继续产品化/教学化增强”的阶段。

### 3.1 Orchestrator Agent 本体

当前状态：

- 已有 `OrchestratorRuntime`
- 已有独立 `OrchestratorAgent` 类，负责身份、prompt、策略 profile、调度解释与 trace/workspace 视角
- 新建运行页会展示锁定启用的 Orchestrator，避免误解其为可关闭的普通子 Agent

当前边界：

- 执行主循环仍在 `OrchestratorRuntime` 中，尚未完全迁移到 `OrchestratorAgent`
- 后续可继续引入 LLM 驱动的 orchestrator decision、可保存策略 profile，以及更强的调度解释 UI

### 3.2 Planner Agent

当前状态：

- 已能优先通过 LLM 生成结构化 plan
- 结构化解析失败时会回退到 `v1 SimplePlanner`
- 已有基础 plan policy，可将修复/实现类任务归一化为更适合教学的顺序
- 已支持按运行级 Agent 配置过滤不可用步骤
- 已支持基于失败上下文的 replan fallback，例如 Tester 失败后优先生成 `Coder -> Tester` 回流计划
- `PlanStep` 已增加 `strategy_explanation / disabled_agent_adjustment / replan_reason`
- Planner 会在 plan metadata 中记录 `planner_strategy`，便于 UI / trace / 教学解释步骤来源
- 禁用 `Tester / Analyst / Reviewer` 时，Runtime 会在保留步骤上补充目标调整说明，例如“未自动验证”“不依赖独立分析产物”

后续增强：

- replan 仍主要是规则 + LLM prompt 增强，还不是完整的策略搜索
- 步骤解释目前是基础规则生成，后续可进一步接入 LLM 生成更自然的教学说明
- 禁用 Agent 后的目标调整已可见，但还没有在 WebUI 中做专门展示

### 3.3 Analyst Agent

当前状态：

- 已能输出项目摘要、模块职责、入口文件、关键文件和编码提示
- 已能识别部分项目画像，例如 Gradle/Kotlin、Python、Node/generic
- 对目录扫描、关键文件读取、结构总结等不同分析模式已有基础区分

后续增强：

- 还没有更深的模块依赖分析
- 还缺少更细粒度的文件级上下文选择策略
- Analyst 输出已经能服务当前 Coder/Tester 主链路，但还不是完整项目理解引擎

### 3.4 Coder Agent

当前状态：

- 已能借助 `v1 AgentLoop` 做实际修改
- 已输出文件变更、diff 预览和风险说明
- 内层 `v1 AgentLoop` 已标记为非顶层 run，避免污染运行历史
- 内层 run 通过 `root_run_id / parent_run_id` 保留追踪关系
- 已输出完整 `patch_diffs`、`patch_stats`、`patch_id`、`base_snapshot_id`、`head_snapshot_id`
- patch artifact 已升级为 `v2.patch_artifact.v1`，包含文件列表、完整 diff、统计信息、风险说明和内外层 run 关系
- workspace artifact metadata 会记录 patch id、快照摘要、统计信息和 loop boundary，便于后续版本治理
- Coder 输出中已包含“两层 loop”边界说明，明确内层 `v1 AgentLoop` 是单任务执行单元，不拥有多 Agent 调度权

后续增强：

- patch artifact 已有版本化 schema 和 snapshot id，但还不是完整 patch repository / 可回滚系统
- 大型二进制文件、超大文本 diff、冲突合并等高级 patch 治理仍未覆盖
- “两层 loop”边界已有结构化说明，但 WebUI 还没有专门的教学展示卡片

### 3.5 Tester Agent

当前状态：

- 已能跑命令并输出结构化测试报告
- 已会优先选择更聚焦的测试命令
- 已支持根据 Gradle/Kotlin 项目画像选择 `compileKotlin / compileKotlinJvm / test` 等候选命令
- 已可通过运行级 Agent 配置跳过

后续增强：

- 构建校验与测试范围控制仍然有限
- 失败原因分类还比较粗糙
- 项目类型识别和验证命令选择还需要更多技术栈覆盖
- Tester 与 Reviewer 的联动已有基础，但还没有形成完整质量门禁策略

### 3.6 Retry / RePlan / Fallback

当前状态：

- 已支持单次失败回流
- 已支持有限 replan
- Tester 失败会优先回流给 Coder，避免直接宣称完成
- RePlan 会携带失败步骤、失败 Agent、测试结果和执行备注等结构化上下文
- Planner 已能基于失败上下文生成基础 fallback replan

后续增强：

- 触发条件仍偏规则化，尚未形成完整策略表或可配置 profile
- retry / replan / fallback 的 UI 解释还不够直观
- fallback 类型仍然有限，主要覆盖 Tester/Coder 失败路径

### 3.7 Trace / Observability

当前状态：

- 结构化 trace 字段已落库并可按 run 查询
- 已有 execution log / delegation tree / execution node 基础视图
- `run_started / agent_selected / delegation_started / delegation_finished / workspace_updated / replan_* / run_finished` 等关键事件已覆盖主链路
- Orchestrator policy、strategy profile、plan explanation、delegation explanation 已进入 trace/workspace
- Debug Replay / WebUI 执行回放已可用于教学演示

后续增强：

- execution node 模型仍是基础版，尚未支持更复杂的分组、折叠和筛选
- session 级 replay 已有基础查询，但还不是完整“课程回放”体验
- 控制台/CLI 链路展示仍需做成更正式的教学输出

---

## 4. 未完成项

### 4.1 Reviewer Agent

当前已实现增强基础版。

已具备：

- 更丰富的规则库覆盖，包括 v1/v2 边界、共享 contract、缺少测试、宽泛异常捕获、公共接口变更、安全敏感模式等。
- 可配置 LLM review 策略，可关闭 LLM 或调整严格度、问题数量与关注点。
- 已支持规则分组开关，可按运行启用/禁用 scope、testing、security、maintainability、boundaries、api、domain。
- 与最近测试结果联动，能识别“测试失败仍未解决”“验证未形成有效结论”等情况，并可配置 `off / suggest / block`。
- 读取 diff preview、改动文件片段和关键文件片段，避免只基于 Coder summary 做 review。
- WebUI `/agents` 页已有 Reviewer 策略配置面板。

还没有：

- 可保存/复用的 Reviewer strategy profile
- run 详情页中的 review 分组统计展示
- 与 Tester 失败回流策略的深度联动

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

当前 registry 主要按 `agent_id` 获取，但已具备运行级 Agent 启用/禁用能力。

还没有：

- 按 capability 查询
- 按任务类型自动选 Agent
- 独立的 Agent 管理接口
- 更细粒度的权限/能力策略

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

当前已支持基础版：

- `SharedMemory`：对 shared workspace 字段提供统一读取与 snapshot 接口
- `PrivateMemory`：对 agent-scoped `private_context` 提供统一读写接口
- `V2MemoryPolicy`：集中定义上下文裁剪策略，包括 execution notes 数量、artifact 数量、列表长度、字符串长度和 dict key 数量
- `V2MemoryManager`：按 Agent 类型选择 shared/private memory，并进行裁剪治理
- `ContextBuilder` 已切换为通过 memory manager 组装上下文，不再散落读取所有 workspace 字段
- `WorkspaceStore` 写入私有上下文时会经过 `PrivateMemory` 抽象

还没有：

- 跨 run 的长期记忆恢复策略
- memory profile 的 UI/API 配置
- 更智能的摘要压缩与重要性评分
- memory 变更的独立 trace 事件与可视化

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
- 运行历史可同时展示 `v1 / v2` 顶层 run
- V2 内部 Coder 子运行已从运行历史中过滤
- WebUI 支持 V2 Agent 运行级勾选配置
- V2 运行记录持久化 `workdir`

后续仍需继续：

- 更清晰的 delegation tree 增强版
- 更面向课程和 UI 的 replay 增强版
- 更清楚地区分“已修改代码”和“已测试通过”的最终答复口径

### P2：进入增强版

当前已完成基础版：

- `ReviewerAgent` 增强基础版
- Reviewer 规则分组、WebUI Agent 配置页、测试失败联动策略
- artifact 管理增强版（基础落库与回放）
- execution node 基础视图
- V2 memory 基础抽象与上下文裁剪策略

后续仍可继续：

- 将 memory 策略升级为可保存 profile，并支持跨 run 恢复
- 继续把 Reviewer 策略从浏览器本地配置升级为后端 profile，并在 run 详情页展示分组统计
- 为未来并行执行和 `v3` 事件驱动保留扩展点

---

## 7. 一句话总结

当前 `v2` 已经具备“中心化多 Agent 编排”的雏形和主链路，但还没有达到最初目标中的完整工程化实现。下一阶段的重点不再是“从零搭骨架”，而是把规划、分析、编码、测试、trace 和 workspace 这些关键环节做扎实。
