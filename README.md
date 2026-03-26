# Simple Code Agent

一个可持续扩展的 Python 项目基础骨架，包含：

- 环境变量读取
- 控制台日志输出
- 清晰的 `app/core` 分层
- 可直接通过模块方式启动
- 可替换的 LLM Provider 抽象
- 基于 Pydantic 的 contract 层

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

## 编程 Demo

可以用下面的脚本生成一套“小范围编程任务”演示工作区：

```bash
.venv/bin/python scripts/setup_coding_demo.py
```

生成后会得到 `demo_workspace/`，其中包含几类典型任务：

- 新建 `StringUtils`
- 为 `TodoService` 新增 CRUD 方法
- 参考 `OrderService` 仿写 `ProductService`
- 修复一个简单单元测试

验证命令示例：

```bash
.venv/bin/pytest demo_workspace/tests/test_string_utils.py
.venv/bin/pytest demo_workspace/tests/test_todo_service.py
.venv/bin/pytest demo_workspace/tests/test_product_service.py
.venv/bin/pytest demo_workspace/tests/test_math_utils.py
```

## 演示 CLI

可以直接用下面的命令跑一次完整任务：

```bash
.venv/bin/python scripts/run_cli.py "解释一下这个类的作用" \
  --version v1 \
  --model your-model \
  --base-url http://localhost:8000/v1 \
  --api-key your-key
```

如果要查看简版 trace：

```bash
.venv/bin/python scripts/run_cli.py "解释一下这个类的作用" \
  --version v1 \
  --model your-model \
  --base-url http://localhost:8000/v1 \
  --api-key your-key \
  --trace
```

## FastAPI 服务

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

查询 Trace：

```bash
curl -s http://127.0.0.1:8000/debug/traces/<run_id>
```

## 启动方式

1. 创建虚拟环境并激活

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

4. 启动项目

```bash
python -m app.main "你好，介绍一下你自己"
```

或使用一键启动脚本：

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
  --base-url http://localhost:8000/v1 \
  --model local-model \
  --api-key test-key \
  --session-id demo-session
```

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
