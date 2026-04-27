# SimpleCodeAgent

一个用于教学和演示的 **编程智能体工程化演进项目**。

这个仓库不是为了做一个“大而全”的 Agent 框架，而是用一套可运行、可观察、可逐步扩展的代码，讲清楚一个 Code Agent 如何从 **单 Agent Runtime** 演进到 **中心化多 Agent 编排系统**。

你可以把它理解为一个系列课程的配套工程：

- `v1`基础课：从零实现一个可运行的单 Agent CodeAgent
- `v2`高级课：在不破坏 v1 的前提下，演进出多 Agent 协作、共享上下文、失败回流和可观测链路

---

## 相关链接

- OpenVitamin：<https://github.com/fengzhizi715/OpenVitamin>
- 课程购买：<https://gttmx.xetlk.com/s/4aaPVM>
- 使用指南：[`docs/usage_guide.md`](docs/usage_guide.md)

---

## 这个项目适合谁

- 想系统学习 Code Agent 内部实现的人
- 想理解 Tool Calling、RAG、Memory、Trace、Runtime Loop 的开发者
- 想了解智能体开发的工程师
- 想从单 Agent 过渡到多 Agent 编排的工程师
- 想了解智能体原理的工程师，而不是只用使用 LangChain、LangGraph 等框架

---

## 你会在这里看到什么

### V1：单 Agent 基础闭环(基础课)

`app/v1` 是一个轻量、稳定、适合教学的单 Agent Runtime，重点讲清楚：

- LLM Provider 抽象
- Agent Runtime Loop
- Tool 注册与调用
- 文件读写、搜索、Shell 执行
- Session Memory
- 单库 RAG 检索
- Simple Planner
- Trace 与运行记录
- CLI / HTTP API 基础入口

### V2：中心化多 Agent 编排(高级课)

`app/v2` 是基于 v1 基础设施演进出来的多 Agent 版本，重点展示：

- Orchestrator 中心化调度
- Planner / Analyst / Coder / Tester / Reviewer 分工
- Agent Registry 与统一 Contract
- Shared Workspace 与 Private Context
- Delegation 委派机制
- Retry / RePlan / Fallback
- Trace / Execution Log / Run Replay
- 多 RAG 支持与运行级 RAG 开关
- WebUI 中的运行、历史、回放、Agent 配置与 RAG 管理

---

## 项目亮点

- 双版本并行：`v1` 保持单 Agent 教学稳定性，`v2` 承载多 Agent 演进。
- 不破坏旧版本：`v2` 复用共享底座，但不反向污染 `v1`。
- 可运行闭环：支持 CLI、FastAPI、WebUI 三种入口。
- 可观测：运行历史、Trace、执行回放、Workspace / Memory 展示。
- 可教学：模块边界清楚，每个阶段都能单独讲解和验证。
- 可扩展：未来可继续演进并行执行、事件驱动、更多 Agent 策略。

---

## 版本定位

| 版本 | 目录 | 定位 | 适合讲解 |
| --- | --- | --- | --- |
| v1 | `app/v1` | 单 Agent Runtime | Agent Loop、Tools、Memory、RAG、Trace |
| v2 | `app/v2` | 中心化多 Agent Runtime | Orchestrator、Delegation、Workspace、RePlan |

### RAG 策略

- v1：严格单库，仅使用默认库 `default`。
- v2：支持 `rag_id` / `rag_ids` 多库检索。
- WebUI：v2 新建运行时可以勾选是否启用 RAG，普通查询可以关闭。

---

## 快速开始

### 1. 创建虚拟环境并安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

最小配置示例：

```env
LLM_BASE_URL=http://127.0.0.1:8000/v1
LLM_AUTH_MODE=service_token
LLM_SERVICE_TOKEN=your-service-token
LLM_MODEL=your-model
WORKDIR=/absolute/path/to/your/project
SESSION_ID=demo-session
```

如果你接的是 OpenVitamin，可先把 `LLM_BASE_URL`、`LLM_SERVICE_TOKEN`、`LLM_MODEL` 替换成 OpenVitamin 对应配置。正式文档链接后续会补到上方占位链接中。

### 3. 启动服务

推荐一键启动 API + WebUI：

```bash
./run-all.sh
```

也可以分别启动：

```bash
# backend
.venv/bin/uvicorn app.api.server:app --host 127.0.0.1 --port 8000

# frontend
./webui/start.sh
```

WebUI 默认地址：

```text
http://localhost:5173
```

---

## 使用示例

### 运行 v1

```bash
.venv/bin/python scripts/run_cli.py "解释这个模块的主要职责" --version v1
```

### 运行 v2

```bash
.venv/bin/python scripts/run_cli.py "先分析项目结构，再给出一个小范围优化建议" --version v2
```

### 指定工作目录

```bash
.venv/bin/python scripts/run_cli.py "帮我分析这个项目的目录结构" \
  --version v2 \
  --workdir /absolute/path/to/project \
  --max-steps 5
```

### 导入 RAG 文档

```bash
.venv/bin/python scripts/ingest_docs.py --file /absolute/path/to/your/file.md
```

---

## WebUI

WebUI 主要用于教学演示、调试和回放。

| 页面 | 路径 | 说明 |
| --- | --- | --- |
| Overview | `/overview` | 系统概况与配置入口 |
| Run | `/run` | 新建 v1 / v2 运行任务 |
| History | `/history` | 运行历史列表 |
| Agents | `/agents` | Agent 列表与 Reviewer 策略配置 |
| RAG | `/rag` | RAG 知识库列表 |
| RAG Detail | `/rag/:ragId` | 指定知识库上传、重建、删除、概览 |
| Run Detail | `/runs/:runId` | 执行详情、Workspace、Memory、Delegation |
| Trace | `/runs/:runId/trace` | Trace 时间线 |

---

## WebUI 截图（占位）

> 下面先保留截图占位。后续把图片放到 `docs/images/` 后，直接替换对应文件即可。

### 1. Overview 页面

![Overview 页面截图占位](docs/images/webui-overview-placeholder.png)

### 2. Run 页面

![Run 页面截图占位](docs/images/webui-run-placeholder.png)

### 3. History 页面

![History 页面截图占位](docs/images/webui-history-placeholder.png)

### 4. RAG 列表页

![RAG 列表页截图占位](docs/images/webui-rag-list-placeholder.png)

### 5. RAG 详情页

![RAG 详情页截图占位](docs/images/webui-rag-detail-placeholder.png)

### 6. 执行详情页

![执行详情页截图占位](docs/images/webui-run-detail-placeholder.png)

### 7. Trace 页面

![Trace 页面截图占位](docs/images/webui-trace-placeholder.png)

---

## API 入口

常用接口：

- `POST /agent/run`：运行任务，支持 `version: v1 | v2`
- `GET /debug/runs`：运行历史
- `GET /debug/v2/runs/{run_id}/replay`：v2 执行回放
- `GET /debug/traces/{run_id}`：Trace 时间线
- `GET /debug/agents`：Agent 列表
- `GET /debug/rag/collections`：列出 RAG 库
- `POST /debug/rag/collections`：创建 RAG 库
- `GET /debug/rag/overview`：查询指定 RAG 库概览
- `POST /debug/rag/upload`：上传并导入文件
- `POST /debug/rag/reindex-source`：重建单文件索引
- `POST /debug/rag/delete-source`：按 source 删除向量分块

---

## 目录结构

```text
app/
  api/          # HTTP 路由与服务入口
  cli/          # CLI 运行封装
  contracts/    # 跨模块协议与 Pydantic schema
  core/         # 配置、日志、异常
  db/           # SQLite 基础能力
  llm/          # LLM Provider 抽象
  trace/        # Trace 记录与查询
  v1/           # 单 Agent 实现
  v2/           # 多 Agent 实现
docs/           # 架构、使用、课程路线文档
scripts/        # 本地脚本入口
webui/          # Vue3 + Vite 前端
```

---

## 文档导航

- 使用指南：[`docs/usage_guide.md`](docs/usage_guide.md)
- 架构说明：[`docs/architecture.md`](docs/architecture.md)
- Runtime 约束：[`docs/agent_runtime.md`](docs/agent_runtime.md)
- Tool 总览：[`docs/tooling.md`](docs/tooling.md)
- RAG 使用：[`docs/rag_usage.md`](docs/rag_usage.md)
- 编程工作流：[`docs/coding_workflow.md`](docs/coding_workflow.md)
- 教学路线：[`docs/teaching_roadmap.md`](docs/teaching_roadmap.md)
- V2 状态：[`docs/v2_status.md`](docs/v2_status.md)

---

## 课程说明

这个项目会长期围绕“如何工程化构建编程智能体”持续演进。课程会优先讲清楚可运行闭环和工程边界，而不是追求一次性堆满所有高级能力。

课程购买链接：

<https://gttmx.xetlk.com/s/4aaPVM>

---

## 设计原则

- 先跑通，再抽象。
- 先保持 v1 稳定，再演进 v2。
- Agent 必须通过 Tool 执行动作。
- Contract 优先，避免在核心边界传裸字典。
- Trace 和运行历史是一等能力，不是附属日志。
- 教学项目要能解释清楚每一层为什么存在。

---

## 当前状态

- v1：稳定教学版，适合讲单 Agent 基础闭环。
- v2：可用增强版，适合讲多 Agent 编排和工程化演进。
- WebUI：已具备运行、历史、回放、Agent 配置、RAG 管理等教学演示能力。
- Reviewer / Memory / Multi-RAG / Workspace 可视化等能力仍在持续增强中。
