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
  main.py
requirements.txt
pyproject.toml
.env.example
README.md
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
