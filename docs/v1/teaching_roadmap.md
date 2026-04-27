# Roadmap（课程 12 节版）

本文档用于把 `Simple Code Agent` 项目路线与课程大纲对齐。目标是让每一节课都能对应到：

- 明确的工程概念
- 可定位的代码目录
- 可复现的课堂 Demo
- 可观测、可验收的学习产出

项目整体遵循：`v1` 作为稳定教学主线，`v2` 作为进阶扩展方向。

---

## 0. 课程总目标与边界

### 总目标

结课时，学员可以独立完成一个轻量编程执行型 CodeAgent，具备：

- 搜索项目代码
- 阅读和理解文件
- 根据 docs 生成/修改简单实现
- 完成小范围 CRUD 与 bugfix
- 执行测试并分析失败
- 输出可查询 Trace

### 边界（避免课程失焦）

- 主线只覆盖 **小范围可验证编程任务**，不追求大规模自动化软件工程。
- `v1` 不演进为复杂 workflow 引擎，复杂编排放到 `v2` 讨论。
- 每节课以「可运行 + 可解释 + 可观测」为第一优先级。

---

## 1. 12 节课程映射（按你的大纲）

### 第 1 节 Agent 工程范式与 CodeAgent 项目路线

**内容对齐**

- AI 应用三阶段：Prompt → Workflow → Agent
- 真正的 Agent Runtime 定义（loop + tool + state + trace）
- CodeAgent 最终 Demo 预览
- 技术栈与目录结构导览
- LLM Provider 抽象思想

**项目落点**

- `README.md`
- `docs/architecture.md`
- `app/llm`
- `app/v1/runtime`

**平台穿插**

- 推理平台价值：模型路由、trace、cost 可观测

---

### 第 2 节 项目初始化与 LLM Provider 实现

**内容对齐**

- 项目结构创建、`config` / `.env`
- logging 规范
- `LLMProvider` 抽象与 OpenAI-compatible client

**Demo**

- CLI 发起一次模型调用

**项目落点**

- `app/core/config.py`
- `app/core/logger.py`
- `app/llm/client.py`
- `scripts/run_cli.py`

---

### 第 3 节 最小 Agent Loop：思考 → 行动 → 结束

**内容对齐**

- message contract
- agent state
- step 执行流程
- final answer 判定

**Demo**

- Agent 完成一个简单问答/阅读任务

**项目落点**

- `app/contracts/message.py`
- `app/contracts/run.py`
- `app/v1/runtime/loop.py`
- `app/v1/runtime/state.py`

---

### 第 4 节 Tool 系统设计：Contract 与 Registry

**内容对齐**

- tool schema
- tool base class
- registry
- tool routing

**Demo**

- 注册 `dummy_tool` 并通过 `ToolRouter` 调用

**平台穿插**

- skill governance
- tool 权限控制

**项目落点**

- `app/contracts/tool.py`
- `app/v1/tools/base.py`
- `app/v1/tools/registry.py`
- `app/v1/tools/router.py`

---

### 第 5 节 代码操作工具：读 / 搜 / 写 / 执行

**内容对齐**

- `read_file`
- `file_search`
- `write_file`
- `shell_run`

**Demo**

- Agent 搜索 TODO 并总结

**项目落点**

- `app/v1/tools/read_file.py`
- `app/v1/tools/file_search.py`
- `app/v1/tools/write_file.py`
- `app/v1/tools/shell_run.py`

---

### 第 6 节 Memory 系统：让 Agent 具备上下文能力

**内容对齐**

- session memory
- context 压缩策略
- memory repository
- 多轮任务串联

**Demo**

- 连续执行多个开发任务并复用上下文

**项目落点**

- `app/v1/memory/session_memory.py`
- `app/v1/memory/repository.py`
- `app/v1/memory/summary_memory.py`
- `app/db`

---

### 第 7 节 RAG：让 Agent 能查文档与规范

**内容对齐**

- chunking
- embedding
- Chroma
- retriever tool

**Demo**

- Agent 根据 docs 写代码

**平台穿插**

- embedding pipeline

**项目落点**

- `app/v1/rag/chunking.py`
- `app/v1/rag/embeddings.py`
- `app/v1/rag/vector_store.py`
- `app/v1/tools/retrieve_docs.py`
- `docs/rag_usage.md`

---

### 第 8 节 Planner：从分析任务到简单编程执行

**内容对齐**

- step list
- 任务拆解
- 执行顺序
- step retry

**Demo**

- “新增一个工具类”任务

**平台穿插**

- DAG / workflow engine（作为对比，不进入 v1 主线实现）

**项目落点**

- `app/v1/planner/simple_planner.py`
- `app/v1/runtime/plan_executor.py`
- `app/v1/runtime/direct_tool_executor.py`

---

### 第 9 节 Runtime 稳定性：避免 Agent 失控

**内容对齐**

- `max_steps`
- timeout
- retry
- error handling
- fallback

**Demo**

- 定位并修复一次“无限循环 / 步数耗尽”问题

**项目落点**

- `app/v1/runtime/loop.py`
- `app/llm/client.py`
- `app/core/exceptions.py`

---

### 第 10 节 Trace 系统：Agent 可观测性

**内容对齐**

- trace event schema
- jsonl recorder
- trace repository
- trace viewer

**Demo**

- 查看一次完整 coding run 的事件时间线

**平台穿插**

- 平台 trace timeline 对照演示

**项目落点**

- `app/contracts/trace.py`
- `app/trace/recorder.py`
- `app/trace/repository.py`
- `scripts/view_trace.py`

---

### 第 11 节 服务化：CLI + FastAPI 接入

**内容对齐**

- run endpoint
- streaming（现状与扩展点）
- `run_id`
- debug trace query

**Demo**

- Postman / curl 调用 Agent 服务

**项目落点**

- `app/api/server.py`
- `app/api/routes/agent.py`
- `app/api/routes/debug.py`
- `app/main.py`

---

### 第 12 节 最终项目：轻量编程执行型 CodeAgent

**最终能力展示**

- Agent 搜索项目代码
- 阅读文件
- 根据 docs 写工具类
- 新增简单 CRUD
- 运行测试
- 修复小 bug
- 输出 trace

**最后升级演示**

- 切换本地推理平台模型
- 多模型路由思想

**项目落点**

- 组合第 2~11 节全部模块做一次端到端验收
- 建议基于第 5、7、9 节的 Demo 组合成端到端基础脚本

---

## 2. 阶段性里程碑（按开课节奏）

### M1（第 1~4 节）：跑通最小闭环

- 产出：能解释架构、能从 CLI 调模型、能注册并路由 `dummy_tool`。
- 验收：学员可独立完成“最小 loop + tool call”演示。

### M2（第 5~8 节）：形成编程执行能力

- 产出：具备读搜写执工具链、memory、RAG、planner 基础能力。
- 验收：学员可完成“根据 docs 新增一个小工具类”任务。

### M3（第 9~12 节）：稳定性与服务化收口

- 产出：具备稳定性治理、trace 观测、API 接入与最终整体验收。
- 验收：学员可提交“可复现 demo + trace 证据 + 简短复盘”。