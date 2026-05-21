# V3 产品化差异路线图

## 标题

让 `v3` 在产品层面明显区别于 `v2` 的 P0 / P1 路线图

---

## 背景

从当前仓库实现来看，`v3` 在**架构层**已经和 `v2` 有明显差异：

- `v2` 核心是中心化多 Agent 编排
- `v3` 核心是 `Graph + Skill + Event + Trigger + Governance` 运行时

但在**用户感知层**，两者差距仍然不够大。

当前用户在 WebUI 中看到的主要仍然是：

- 输入一个任务
- 系统执行
- 返回结果

如果一次 `v3` 运行没有真正进入：

- `event -> trigger -> follow-up`
- `governance intercept`
- `replay / audit`

那么它在产品体验上就会非常像“换了执行内核的 `v2`”。

因此，这份路线图的目标不是继续增加更多内部模块，而是：

> 让用户在产品界面、执行过程与结果解释上，明显感受到 `v3` 是一个结构化 runtime，而不是另一个多 Agent 页面。

---

## 一句话目标

### P0

在 `1` 周左右的成本内，让用户**一眼看出** `v3` 和 `v2` 的差异。

### P1

在额外 `1-2` 周的成本内，让用户**真实感受到** `v3` 的行为模式与 `v2` 不同。

---

## 当前判断

当前 `v3` 的主要问题不是“没有能力”，而是“差异没有被产品化表达出来”。

具体表现为：

1. `v3` 的第一页仍然经常像结果页，而不是 runtime 页
2. `event / trigger / autonomy / governance / replay` 虽然存在，但没有形成强感知主路径
3. 用户不知道这次运行到底是：
   - 纯 graph 执行
   - graph + trigger
   - graph + autonomy follow-up
4. 很多 `v3` 特有信息仍然停留在调试视角，而不是用户可理解视角

因此，改造优先级应该是：

1. 先做“可感知差异”
2. 再做“可验证能力差异”

而不是继续堆更多底层能力名词。

---

## P0

### 定位

`P0` 是“展示差异版”。

目标不是把 `v3` 做成完整自治平台，而是让用户立刻理解：

- `v2` 在做协作编排
- `v3` 在做 runtime 推进

### 时间预估

- `1` 名熟悉仓库的人
- 约 `4-7` 个工作日

### 范围

#### 1. 明确展示本次运行模式

在 `v3` 任务详情和 `Autonomy` 页中，明确展示一次运行属于哪一种模式：

- `Graph Only`
- `Graph + Trigger`
- `Graph + Autonomy Follow-up`
- `Graph + Governance Intercept`

要求：

- 第一屏可见
- 不藏在原始 JSON 中
- 能被用户一眼读懂

价值：

- 用户能立刻知道这次 `v3` 是否真的进入了 runtime 特有路径

#### 2. 把 event-trigger-follow-up 做成显式流程卡

不要只展示 trace 表格。

应新增更强表达力的流程卡，明确说明：

- 发生了什么 event
- 命中了哪条 trigger
- 触发了哪个 follow-up skill
- 最终结果是什么

要求：

- 支持“无 follow-up”时也明确显示
- 支持“被 governance 拦截”时明确显示 stop reason

价值：

- 这会直接把 `v3` 和 `v2` 的体验拉开

#### 3. 给 governance 做解释层

当前 `governance` 信息更多是调试字段。

`P0` 需要把它收敛成用户可读说明，例如：

- 为什么允许继续执行
- 为什么拦截
- 为什么进入 cooldown
- 为什么停止传播

建议展示为：

- `Allowed`
- `Blocked`
- `Cooled Down`
- `Propagation Limited`
- `Budget Exhausted`

价值：

- 这是 `v3` 的关键辨识度来源之一

#### 4. 强化 Autonomy 页作为 runtime 入口

`Autonomy` 页不应只是“另一个详情页集合”。

`P0` 要把它强化为：

- `Overview`
- `Graph`
- `Events`
- `Triggers`
- `Runtime Status`

要求：

- 第一屏就能看出它是“系统视角”
- 和任务详情形成清晰分工

分工建议：

- 任务详情：结果优先
- Autonomy：运行时优先

#### 5. 预置 2-3 个 v3 demo 场景

如果没有典型场景，用户很难感知 `v3` 的价值。

建议至少准备：

1. `测试失败 -> 自动补救 -> 再测`
2. `代码变更 -> 自动 follow-up test`
3. `事件命中但被 governance 拦截`

要求：

- 页面可直接看出每个场景的链路
- 能用于课程演示和产品区分

### P0 不做

- 不做长期 monitor
- 不做复杂 scheduler 编排
- 不做跨运行 audit 平台
- 不做完整 replay cockpit

### P0 验收标准

满足以下条件，可认为 `P0` 达标：

1. 新用户第一次看 `v3` 页面时，能说出“这不是 `v2` 的换皮”
2. 至少一个 demo 场景能清楚展示 `event -> trigger -> follow-up`
3. 至少一个 demo 场景能清楚展示 `governance intercept`
4. `Autonomy` 页与任务详情的职责边界清楚

---

## P1

### 定位

`P1` 是“真实能力差异版”。

目标不是只让 `v3` 看起来不同，而是让它在行为上确实不同。

### 时间预估

- 在 `P0` 基础上追加
- 约 `1-2` 周

### 范围

#### 1. 把 trigger recovery 做成主路径能力

`P1` 应把 `trigger recovery` 从“存在于代码中”提升为“产品可见主路径”。

重点场景：

- `test_failed -> coding -> test_runner`
- 恢复成功后在最终 report 中收敛
- 恢复失败后明确记录 stop reason

要求：

- 前端能明确区分主 graph 节点与 trigger 虚拟节点
- 最终答案能解释 recovery 是否发生、是否成功

#### 2. 做系统级 replay / audit 入口

`P1` 应让 replay / audit 从“调试能力”变成“产品能力”。

至少支持：

- `replay by run`
- `replay by chain`
- `why triggered`
- `why stopped`

要求：

- 入口在 `Autonomy` 中稳定可见
- 不要求 deterministic replay
- 重点是“解释”和“重看”

#### 3. 做跨运行 trigger / governance 面板

`P1` 应支持从单次 run 跳出来看系统规律。

至少展示：

- 哪些 trigger 常命中
- 哪些 trigger 常被拦截
- 哪些规则常进入 cooldown
- 哪些 run 更容易触发 recovery

价值：

- 一旦进入“跨运行观察”，`v3` 和 `v2` 的产品形态会明显分开

#### 4. 引入真正的 monitor / follow-up 场景

这是 `v3` 从“静态 runtime”进入“有限主动 runtime”的关键一步。

建议选择一个最小场景：

- `CodeChanged -> emit event -> schedule follow-up test`

要求：

- 明确受控
- 明确可停
- 明确可审计

不要求：

- 长时间后台服务做到企业级
- 任意目录监控
- 多节点调度

#### 5. 结果答案中加入 runtime 解释摘要

`P1` 的最终答案不应只说“改了什么”，还应说明：

- 是否触发了 follow-up
- 是否经过 governance
- 是否发生 recovery
- 是否留下 replay / audit 入口

价值：

- 让 `v3` 的“结构化 runtime”身份进入最终交付文本

### P1 不做

- 不做开放式自治系统
- 不做无限目标生成
- 不做复杂分布式 scheduler
- 不做“自由群聊式多 Agent runtime”

### P1 验收标准

满足以下条件，可认为 `P1` 达标：

1. 至少一个真实运行场景会自动进入 trigger recovery 主路径
2. 用户能直接从 UI 看见 replay / audit 的解释价值
3. 用户能跨运行观察 trigger 与 governance 规律
4. 用户能明显感受到 `v3` 是“runtime 在推进”，而不是“多 Agent 在协作”

---

## 推荐实施顺序

建议按以下顺序推进：

### 第 1 步

先完成 `P0` 的运行模式展示与差异表达：

- 运行模式标签
- event-trigger-follow-up 流程卡
- governance explain

### 第 2 步

完成 `Autonomy` 页强化与 demo 场景：

- runtime 入口强化
- 典型 demo 路径

### 第 3 步

推进 `P1` 的 recovery / replay / audit：

- trigger recovery 主路径
- replay / audit 入口

### 第 4 步

最后再引入 monitor / cross-run 面板：

- 跨运行 trigger 观察
- follow-up monitor 场景

---

## 风险与注意事项

### 1. 不要把 `v3` 做成“更多页面的 v2”

如果只是：

- 多几个 tab
- 多几个 JSON 面板
- 多几个 trace 表格

那用户仍然不会觉得它和 `v2` 有本质差异。

### 2. 不要先追求复杂自治

如果太早做：

- scheduler
- monitor
- long-running
- 复杂 policy

很容易把项目拉进实现泥潭，但用户仍然感知不到价值。

### 3. 差异感首先来自“可解释链路”

真正最值钱的不是功能名词，而是：

- 发生了什么
- 为什么继续
- 为什么停止
- 谁做的下一步

这才是 `v3` 产品化的核心。

---

## 最终结论

如果目标只是让用户**明显感觉 `v3` 和 `v2` 不一样**，优先做 `P0`，成本约 `4-7` 个工作日。

如果目标是让 `v3` **在产品能力上真实拉开与 `v2` 的差距**，则需要继续推进 `P1`，整体成本约再加 `1-2` 周。

一句话总结：

> `P0` 解决“看起来不一样”，`P1` 解决“行为上真的不一样”。
