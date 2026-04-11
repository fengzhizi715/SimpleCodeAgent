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
  contracts/    # 跨模块共享的数据协议
  core/         # 配置、日志、异常等基础能力
  db/           # SQLite 连接与迁移
  llm/          # LLM Provider 抽象与适配
  trace/        # Trace 记录、存储与展示
  v1/           # 当前单 Agent 版本实现
    memory/     # 会话记忆与摘要记忆
    planner/    # 任务拆解与步骤规划
    rag/        # 文档切分、向量化与检索
    runtime/    # Agent 主循环、执行器与上下文
    tools/      # 工具定义、注册与代码操作工具
  v2/           # 后续多 Agent 版本预留
docs/           # 项目文档与使用手册
scripts/        # 本地运行、导入和调试脚本
demo_workspace/ # 编程任务演示工作区
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
- [docs/demo_scenarios.md](docs/demo_scenarios.md)

其中包含：

- CLI 用法
- Demo 演示脚本与推荐提示词
- `SESSION_ID` 默认会话行为
- 项目级 session 自动派生
- `WORKDIR` / `--workdir` 用法
- RAG 文档导入与单文件导入
- 如何触发 RAG 检索
- `local_ai_inference_platform` 接入建议
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
- `LLM_AUTH_MODE`：鉴权方式，支持 `auto`、`bearer`、`service_token`、`none`
- `LLM_API_KEY`：调用模型的 API Key
- `LLM_SERVICE_TOKEN`：用于 `X-Service-Token` 的服务令牌
- `LLM_MODEL`：模型名
- `LLM_TIMEOUT`：请求超时时间，单位秒
- `LLM_REASONING_PARAM_STYLE`：控制 `reasoning_mode` 如何映射到 Provider 请求参数
  - `none`：不映射，只作为运行元数据保留
  - `reasoning_effort`：映射为 `reasoning_effort=<mode>`
  - `reasoning_object`：映射为 `reasoning={"effort": "<mode>"}`
  - 具体使用哪一种，取决于你接入的 OpenAI-compatible 服务支持哪种字段风格
- `SESSION_ID`：默认会话 ID。`.env` 或系统环境变量中配置后，CLI 和 `./start.sh` 在未显式传 `--session-id` 时都会使用它
- `WORKDIR`：默认目标工作目录。配置后，CodeAgent 会在这个目录下进行读写、搜索和 shell 执行

当同时使用 `SESSION_ID` 和 `WORKDIR` 时，系统会自动派生项目级 session id，避免同一个会话在不同项目之间串上下文。

CLI 和模块入口还会输出：

- `Direct Tool Execution Used`

该字段表示当前运行是否使用了 planner 的确定性工具执行路径，而不是完全依赖模型主动发起 `tool_calls`。

## 日志说明

项目当前同时输出控制台日志和文件日志。

日志文件默认保存在项目根目录下的 `logs/`：

```text
logs/app.log
```

文件日志按天滚动，并默认只保留最近 30 天，避免日志长期无限增长。

日志格式如下：

```text
2026-04-10 21:00:00 | INFO | app.llm.client | run_id=... | session_id=... | Sending LLM request: model=...
```

日志至少包含：

- 时间
- 级别
- 模块名
- `run_id`
- `session_id`
- 明确消息

因此排查时可以很快判断：

- 是哪一层输出的日志
- 是 `INFO` 还是 `ERROR`
- 是配置装配问题、模型调用问题，还是工具执行问题

可以通过 `LOG_LEVEL` 控制日志级别，例如：

```env
LOG_LEVEL=INFO
```

## 当前限制

- `v2` 入口只预留，还没有多 Agent 实现
- 当前默认 Provider 是 OpenAI-compatible 协议
- streaming API 还没有接入

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
