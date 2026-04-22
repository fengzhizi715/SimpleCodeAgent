# Simple Code Agent

一个用于演示编程智能体演进路径的 Python 项目。

当前仓库采用单仓库双版本结构：

- `app/v1`：当前可运行的单 Agent 版本
- `app/v2`：预留给后续多 Agent 编程智能体

当前已经具备这些能力：

- OpenAI-compatible LLM Provider 抽象
- Pydantic contract 层
- Tool Registry 与代码操作工具
- Session memory 与 SQLite 持久化
- Planner + Agent loop
- RAG 文档导入与检索
- Trace 记录、查看与 API 查询
- CLI 与 FastAPI 服务入口
- 统一日志输出

## 快速开始

1. 创建并激活虚拟环境

```bash
python -m venv .venv
source .venv/bin/activate
```

2. 安装依赖

```bash
pip install -r requirements.txt
```

3. 配置环境变量

```bash
cp .env.example .env
```

4. 填写至少这几个配置

```env
LLM_BASE_URL=http://127.0.0.1:8000/v1
LLM_AUTH_MODE=service_token
LLM_SERVICE_TOKEN=your-service-token
LLM_MODEL=your-model
SESSION_ID=demo-session
WORKDIR=/absolute/path/to/your/project
```

5. 运行一个最小任务

```bash
.venv/bin/python scripts/run_cli.py "解释一下这个类的作用" \
  --version v1
```

如果你在 `.env` 里配置了 `SESSION_ID`，连续运行时会默认落到同一个会话。

## 目录结构

```text
app/
  api/          # HTTP 服务入口与路由
  cli/          # CLI 入口复用的参数与执行封装
  contracts/    # 跨模块共享的数据协议
  core/         # 配置、日志、异常等基础能力
  db/           # SQLite 连接与迁移
  llm/          # LLM Provider 抽象与适配
  trace/        # Trace 记录、存储与展示
  v1/           # 当前单 Agent 版本实现
    memory/     # 会话记忆与摘要记忆
    planner/    # 任务拆解与步骤规划
    rag/        # 文档切分、向量化与检索
    runtime/    # Agent 主循环、规划执行与 direct tool 执行
    tools/      # 工具定义、注册与代码操作工具
  v2/           # 后续多 Agent 版本预留
docs/           # 项目文档与使用手册
scripts/        # 本地运行、导入和调试脚本
demo_workspace/ # 编程任务演示工作区
logs/           # 按天滚动的运行日志（默认保留 30 天）
```

## 版本说明

- `v1`：当前默认版本，已实现单 Agent runtime、planner、memory、tools、rag
- `v2`：当前只预留目录和入口参数，尚未实现

当前 CLI 与 API 都支持显式传 `version`：

- CLI：`--version v1|v2`
- API：请求体中的 `"version": "v1" | "v2"`

目前传 `v2` 会返回“已预留但尚未实现”的明确错误，不会静默回退到 `v1`。

## 使用说明

详细使用手册见：

- [docs/usage_guide.md](docs/usage_guide.md)

其中包含：

- CLI 用法
- Demo 演示脚本与推荐提示词
- `SESSION_ID` 默认会话行为
- 项目级 session 自动派生
- `WORKDIR` / `--workdir` 用法
- RAG 文档导入与单文件导入
- 如何触发 RAG 检索
- `OpenVitamin` 接入建议
- FastAPI 调用方式
- Trace 查看
- Coding demo 演示流程

单文件导入示例：

```bash
.venv/bin/python scripts/ingest_docs.py --file /absolute/path/to/file.docx
```

开发者架构说明见：

- [docs/architecture.md](docs/architecture.md)
- [docs/roadmap.md](docs/roadmap.md)
- [docs/demo_scenarios.md](docs/demo_scenarios.md)

## 常用入口

模块入口（快速本地验证）：

```bash
python -m app.main "你好，介绍一下你自己" --version v1
```

启动脚本：

```bash
./start.sh "你好，介绍一下你自己"
```

## 文档导航

- 使用与演示：[`docs/usage_guide.md`](docs/usage_guide.md)
- 架构与边界：[`docs/architecture.md`](docs/architecture.md)
- Runtime 约束：[`docs/agent_runtime.md`](docs/agent_runtime.md)
- Tool 总览：[`docs/tooling.md`](docs/tooling.md)
- RAG 使用：[`docs/rag_usage.md`](docs/rag_usage.md)
- 编程工作流：[`docs/coding_workflow.md`](docs/coding_workflow.md)
- 演示脚本：[`docs/demo_scenarios.md`](docs/demo_scenarios.md)
- 演进路线：[`docs/roadmap.md`](docs/roadmap.md)

## 当前限制

- `v2` 入口只预留，还没有多 Agent 实现
- 当前默认 Provider 是 OpenAI-compatible 协议
- streaming API 还没有接入