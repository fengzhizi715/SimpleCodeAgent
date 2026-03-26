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
LLM_BASE_URL=http://localhost:8000/v1
LLM_API_KEY=your-key
LLM_MODEL=your-model
```

5. 运行一个最小任务

```bash
.venv/bin/python scripts/run_cli.py "解释一下这个类的作用" \
  --version v1
```

## 目录结构

```text
app/
  core/
    config.py
    constants.py
    exceptions.py
    logger.py
  contracts/
    message.py
    tool.py
    run.py
    trace.py
    planner.py
    memory.py
  llm/
    client.py
    parser.py
    schemas.py
  db/
    sqlite.py
    migrations.py
  trace/
    events.py
    recorder.py
    repository.py
    viewer.py
  api/
    deps.py
    server.py
    routes/
      agent.py
      debug.py
  v1/
    runtime/
      context.py
      state.py
      executor.py
      loop.py
    memory/
      base.py
      session_memory.py
      summary_memory.py
      repository.py
    planner/
      base.py
      simple_planner.py
    tools/
      base.py
      registry.py
      read_file.py
      file_search.py
      write_file.py
      shell_run.py
      list_dir.py
      replace_in_file.py
      append_file.py
      retrieve_docs.py
    rag/
      chunking.py
      embeddings.py
      vector_store.py
      ingest.py
      retriever.py
  v2/
  main.py
requirements.txt
pyproject.toml
.env.example
README.md
```

## 版本说明

- `v1`：当前默认版本，已实现单 Agent runtime、planner、memory、tools、rag
- `v2`：当前只预留目录和入口参数，尚未实现

当前 CLI 与 API 都支持显式传 `version`：

- CLI：`--version v1|v2`
- API：请求体中的 `"version": "v1" | "v2"`

目前传 `v2` 会返回“已预留但尚未实现”的明确错误，不会静默回退到 `v1`

## 使用说明

推荐按下面顺序体验项目：

1. 用 CLI 跑一个最小问答任务
2. 导入 docs 文档，体验 RAG 检索
3. 运行 API 服务，用 Swagger 或 curl 调用
4. 查看某次 run 的 trace
5. 生成 coding demo，做编程任务演示

### 1. CLI 使用

最小调用：

```bash
.venv/bin/python scripts/run_cli.py "解释一下这个类的作用" \
  --version v1 \
  --model your-model \
  --base-url http://localhost:8000/v1 \
  --api-key your-key
```

带 session 连续提问：

```bash
.venv/bin/python scripts/run_cli.py "第一问" \
  --version v1 \
  --session-id demo-session

.venv/bin/python scripts/run_cli.py "第二问，继续刚才的话题" \
  --version v1 \
  --session-id demo-session
```

打印简版 trace：

```bash
.venv/bin/python scripts/run_cli.py "解释一下这个类的作用" \
  --version v1 \
  --trace
```

### 2. RAG 文档导入与检索

先导入 `docs/` 下的示例文档：

```bash
.venv/bin/python scripts/ingest_docs.py --docs-dir docs
```

导入后，Agent 在执行时可以通过 `retrieve_docs` 工具检索文档片段。

仓库内置的示例文档包括：

- [docs/agent_runtime.md](/Users/tony/PycharmProjects/SimpleCodeAgent/docs/agent_runtime.md)
- [docs/coding_workflow.md](/Users/tony/PycharmProjects/SimpleCodeAgent/docs/coding_workflow.md)
- [docs/rag_usage.md](/Users/tony/PycharmProjects/SimpleCodeAgent/docs/rag_usage.md)
- [docs/tooling.md](/Users/tony/PycharmProjects/SimpleCodeAgent/docs/tooling.md)

### 3. 生成演示工作区

```bash
.venv/bin/python scripts/setup_coding_demo.py
```

然后可以让 Agent 执行类似任务：

- 新建 `StringUtils`
- 为 `TodoService` 增加 CRUD 方法
- 参考 `OrderService` 仿写 `ProductService`
- 修复简单测试

验证命令示例：

```bash
.venv/bin/pytest demo_workspace/tests/test_string_utils.py
.venv/bin/pytest demo_workspace/tests/test_todo_service.py
.venv/bin/pytest demo_workspace/tests/test_product_service.py
.venv/bin/pytest demo_workspace/tests/test_math_utils.py
```

### 4. FastAPI 服务

启动服务：

```bash
.venv/bin/uvicorn app.api.server:app --host 127.0.0.1 --port 8000
```

Swagger 文档：

```text
http://127.0.0.1:8000/docs
```

运行 Agent：

```bash
curl -s http://127.0.0.1:8000/agent/run \
  -H 'Content-Type: application/json' \
  -d '{
    "task": "解释一下这个类的作用",
    "version": "v1",
    "model": "your-model",
    "base_url": "http://localhost:8000/v1",
    "api_key": "your-key",
    "include_trace": true
  }'
```

查询 trace：

```bash
curl -s http://127.0.0.1:8000/debug/traces/<run_id>
```

### 5. 查看 Trace 时间线

除了 API，还可以直接用脚本查看 trace：

```bash
.venv/bin/python scripts/view_trace.py <run_id>
```

## 启动方式

模块入口仍然保留，适合快速本地验证：

```bash
python -m app.main "你好，介绍一下你自己" --version v1
```

也可以用一键脚本：

```bash
./start.sh "你好，介绍一下你自己"
```

## 环境变量

- `APP_ENV`：运行环境，例如 `development`
- `LOG_LEVEL`：日志级别，例如 `INFO`
- `DEBUG`：是否开启调试，`true` 或 `false`
- `LLM_BASE_URL`：OpenAI-compatible 服务地址
- `LLM_API_KEY`：调用模型的 API Key
- `LLM_MODEL`：模型名
- `LLM_TIMEOUT`：请求超时时间，单位秒

## LLM CLI

支持通过参数覆盖 `.env` 中的配置：

```bash
python -m app.main "写一句话介绍上海" \
  --version v1 \
  --base-url http://localhost:8000/v1 \
  --model local-model \
  --api-key test-key \
  --session-id demo-session
```

## 当前限制

- `v2` 入口只预留，还没有多 Agent 实现
- 当前默认 Provider 是 OpenAI-compatible 协议
- streaming API 还没有接入
- 目前 README 主要面向本地开发与演示，不是生产部署文档

## 验收

满足以下目标：

- 能读取 `.env`
- 日志能正常输出
- `python -m app.main "hello"` 能发起模型调用
- 支持切换模型名和 `base_url`
- 核心对象通过 Pydantic 校验
- 最小 Agent Loop 能生成 `run_id` 并累计 `step_count`
- Tool call 能执行并把结果回传到下一轮 LLM
- 提供基础代码操作工具集
- 统一约定工具错误处理：收到 `ok=false` 后先诊断再决定是否重试
- 支持基于 SQLite 的 session memory
- 提供统一 SQLite 持久化层，保存 session / run / trace metadata
- 支持简单 Planner：拆解复杂任务并顺序执行步骤
- CLI / API 支持显式 `version` 选择入口
