# SimpleCodeAgent

一个用于演示 **编程智能体工程化演进** 的开源项目：  
在同一仓库中同时维护可运行的 `v1`（单 Agent）与 `v2`（中心化多 Agent）。

---

## 项目亮点

- 双版本共存：`v1` 稳定教学闭环 + `v2` 多 Agent 编排演进
- 完整运行入口：CLI、FastAPI、Web UI（Vite）
- 可观测性：Trace 事件、运行历史、回放与执行详情页面
- RAG 能力：文档导入、向量检索、RAG 库管理
- 工程化边界清晰：`core/contracts/trace/api` 与 `v1/v2` 实现层分离

---

## 版本定位

- `app/v1`：单 Agent Runtime（稳定、可预测、便于教学）
- `app/v2`：中心化多 Agent Runtime（可用阶段/Beta，Orchestrator + Planner/Analyst/Coder/Tester/Reviewer）

### RAG 策略（当前版本）

- **v1：严格单库**
  - 仅允许默认库 `default`
  - 任意路径不支持多库并查
- **v2：支持多库**
  - 支持 `rag_id` 与 `rag_ids`
  - 支持多库并查与统一重排
  - 对 `rag_id` 做严格规范化校验（与创建接口一致）

---

## 快速开始

### 1) 创建虚拟环境并安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) 配置环境变量

```bash
cp .env.example .env
```

最小可用配置示例：

```env
LLM_BASE_URL=http://127.0.0.1:8000/v1
LLM_AUTH_MODE=service_token
LLM_SERVICE_TOKEN=your-service-token
LLM_MODEL=your-model
WORKDIR=/absolute/path/to/your/project
SESSION_ID=demo-session
```

### 3) 运行方式

一键启动 API + Web UI（推荐）：

```bash
./run-all.sh
```

或分别启动：

```bash
# backend
.venv/bin/uvicorn app.api.server:app --host 127.0.0.1 --port 8000

# frontend
./webui/start.sh
```

---

## 使用示例

### CLI

```bash
.venv/bin/python scripts/run_cli.py "解释这个模块的主要职责" --version v1
```

```bash
.venv/bin/python scripts/run_cli.py "先分析再改代码并执行测试" --version v2
```

### 文档导入（RAG）

```bash
.venv/bin/python scripts/ingest_docs.py --file /absolute/path/to/your/file.md
```

---

## Web UI 页面

默认地址：`http://localhost:5173`

- `/overview`：系统概况与运行状态
- `/run`：任务运行入口（支持 v1/v2）
- `/history`：运行历史与回放入口
- `/agents`：Agent 列表
- `/rag`：RAG 列表页（创建/查看各知识库）
- `/rag/:ragId`：RAG 详情页（该库上传、重建、删除、概览）
- `/runs/:runId`：执行详情
- `/runs/:runId/trace`：Trace 时间线

---

## Web UI 截图（占位）

> 说明：下面先保留占位，你后续把图片放到 `docs/images/`（或你自己的目录）后，直接替换链接即可。

### 1) Overview 页面

![Overview 页面截图占位](docs/images/webui-overview-placeholder.png)

### 2) Run 页面

![Run 页面截图占位](docs/images/webui-run-placeholder.png)

### 3) History 页面

![History 页面截图占位](docs/images/webui-history-placeholder.png)

### 4) RAG 列表页

![RAG 列表页截图占位](docs/images/webui-rag-list-placeholder.png)

### 5) RAG 详情页

![RAG 详情页截图占位](docs/images/webui-rag-detail-placeholder.png)

### 6) 执行详情页

![执行详情页截图占位](docs/images/webui-run-detail-placeholder.png)

### 7) Trace 页面

![Trace 页面截图占位](docs/images/webui-trace-placeholder.png)

---

## API 入口（简要）

- `POST /agent/run`：运行任务（`version: v1|v2`）
- `GET /debug/rag/collections`：列出 RAG 库
- `POST /debug/rag/collections`：创建 RAG 库
- `GET /debug/rag/overview`：查询指定库概览
- `POST /debug/rag/upload`：上传并导入文件
- `POST /debug/rag/reindex-source`：重建单文件索引
- `POST /debug/rag/delete-source`：按 source 删除向量分块

---

## 目录结构

```text
app/
  api/          # HTTP 路由与服务入口
  cli/          # CLI 运行封装
  contracts/    # 跨模块协议（Pydantic）
  core/         # 配置、日志、异常
  db/           # SQLite 基础能力
  llm/          # LLM Provider 抽象
  trace/        # Trace 记录与查询
  v1/           # 单 Agent 实现
  v2/           # 多 Agent 实现
docs/           # 架构与使用文档
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
- 演进路线：[`docs/teaching_roadmap.md`](docs/teaching_roadmap.md)
- V2 状态：[`docs/v2_status.md`](docs/v2_status.md)

---
