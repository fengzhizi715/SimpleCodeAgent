# 使用说明

本文档用于说明如何在本地运行和演示 `Simple Code Agent`（`v1` 主线 + `v2` MVP）。

如果你准备继续维护项目实现，而不是只做使用验证，建议同时阅读：

- [architecture.md](./architecture.md)
- [AGENTS.md](../AGENTS.md)

## 导航（建议先读）

如果你是第一次上手，推荐按下面顺序阅读：

1. [1. 环境准备](#1-环境准备)
2. [2. CLI 使用](#2-cli-使用)
3. [5. FastAPI 服务](#5-fastapi-服务)
4. [5.1 Web UI（V2 演示，可选）](#51-web-uiv2-演示可选)
5. [4. RAG 文档导入](#4-rag-文档导入)
6. [11. 常见问题](#11-常见问题)

快速路径（最少命令）：

- 一键起全栈：`./run-all.sh`
- 最小 CLI：`.venv/bin/python scripts/run_cli.py "hello" --version v1`
- Web UI 默认地址：`http://127.0.0.1:5173`

## 1. 环境准备

创建并激活虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate
```

安装依赖：

```bash
pip install -r requirements.txt
```

复制环境变量模板：

```bash
cp .env.example .env
```

至少配置以下变量：

```env
LLM_BASE_URL=http://127.0.0.1:8000/v1
LLM_AUTH_MODE=service_token
LLM_SERVICE_TOKEN=your-service-token
LLM_MODEL=your-model
SESSION_ID=demo-session
WORKDIR=/absolute/path/to/your/project
```

如果你接的是 `OpenVitamin`，推荐直接使用 `service token` 鉴权，而不是 Bearer API Key。

推荐配置说明：

- `LLM_BASE_URL` 使用 `http://127.0.0.1:8000/v1`
- `LLM_AUTH_MODE` 使用 `service_token`
- `LLM_SERVICE_TOKEN` 使用你申请好的服务令牌
- `SESSION_ID` 可以固定成一个演示会话名，方便连续提问
- `WORKDIR` 可以固定成你要分析的本地项目根目录

## 2. CLI 使用

最小调用：

```bash
.venv/bin/python scripts/run_cli.py "解释一下这个类的作用" \
  --version v1 \
  --reasoning-mode medium \
  --model your-model \
  --base-url http://127.0.0.1:8000/v1 \
  --service-token your-service-token
```

分析其他本地项目时，可以显式指定目标目录：

```bash
.venv/bin/python scripts/run_cli.py "帮我分析这个项目的目录结构" \
  --version v1 \
  --workdir /Users/tony/PycharmProjects/local_ai_inference_platform
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

也可以直接在环境变量里固定一个默认会话：

```bash
export SESSION_ID=demo-session
.venv/bin/python scripts/run_cli.py "第一问" --version v1
.venv/bin/python scripts/run_cli.py "第二问" --version v1
```

默认会话的优先级是：

1. 显式传入的 `--session-id`
2. 当前 shell 中导出的 `SESSION_ID`
3. `.env` 中配置的 `SESSION_ID`
4. 若都没有，则自动生成新的 `session_id`

`./start.sh` 和 CLI 都遵循这个规则。

如果同时指定了 `session_id` 和 `workdir`，系统会自动把它派生成“项目级 session id”，避免同一个会话在不同项目之间复用旧上下文。
例如 `demo-session` 在不同项目下会变成不同的实际 session 标识。

限制最大执行步数：

```bash
.venv/bin/python scripts/run_cli.py "解释一下这个类的作用" \
  --version v1 \
  --max-steps 5
```

指定 reasoning 模式标记：

```bash
.venv/bin/python scripts/run_cli.py "解释一下这个类的作用" \
  --version v1 \
  --reasoning-mode high
```

如果你希望把 `reasoning_mode` 真正传给底层 Provider，而不仅仅作为运行元数据记录，需要额外配置环境变量：

```env
LLM_REASONING_PARAM_STYLE=none
```

可选值说明：

- `none`
  - 不向 Provider 额外传递 reasoning 参数
  - `reasoning_mode` 仅保留在运行结果、日志和观测信息中
- `reasoning_effort`
  - 将 `reasoning_mode` 映射为 `reasoning_effort=<mode>`
- `reasoning_object`
  - 将 `reasoning_mode` 映射为 `reasoning={"effort": "<mode>"}`

应该选择哪一种，取决于你当前接入的 OpenAI-compatible 服务支持哪种请求字段风格。
如果不确定，建议先用 `none`，确认服务协议后再切换。

打印简版 trace：

```bash
.venv/bin/python scripts/run_cli.py "解释一下这个类的作用" \
  --version v1 \
  --trace
```

查看 V2 默认 Agent 角色矩阵（教学/debug）：

```bash
.venv/bin/python scripts/run_cli.py debug agent-matrix
```

该命令会打印当前默认注册的角色、实现类和 capabilities，便于课堂展示 “planner / analyst / coder / tester / reviewer” 的分工。

`v2` 已可运行（MVP 阶段），可以用下面命令快速验证：

```bash
.venv/bin/python scripts/run_cli.py "hello" --version v2
```

`v2` 当前定位是“中心化多 Agent MVP 骨架”，能力仍在持续增强，详细状态见 `docs/v2_status.md`。

CLI 运行完成后还会额外输出：

- `Reasoning Mode`
- `Direct Tool Execution Used`
- `Usage`
- `Metrics`

其中：

- `Direct Tool Execution Used: yes`
  - 表示本次运行中，planner 的某些步骤没有完全依赖模型主动发起 `tool_calls`
  - runtime 直接执行了明确的工具步骤，例如 `list_dir`、`read_file`、`file_search`，或在生成结构化 JSON 后补执行了 `write_file`
- `Direct Tool Execution Used: no`
  - 表示本次运行仍然主要依赖模型驱动的普通执行路径

## 3. 模块入口

如果你只想快速验证项目主入口，也可以直接运行：

```bash
python -m app.main "你好，介绍一下你自己" --version v1
```

或者使用启动脚本：

```bash
./start.sh "你好，介绍一下你自己"
```

如果 `.env` 中已经配置了 `SESSION_ID`，或者当前 shell 已经 `export SESSION_ID=...`，那么连续执行 `./start.sh` 会默认进入同一个 session。

## 4. RAG 文档导入

先导入 `docs/` 目录下的示例文档：

```bash
.venv/bin/python scripts/ingest_docs.py --docs-dir docs
```

如果只想导入单个文件，也可以直接指定绝对路径：

```bash
.venv/bin/python scripts/ingest_docs.py --file /absolute/path/to/file.pdf
```

导入完成后，Agent 在执行过程中可以通过 `retrieve_docs` 工具检索这些文档片段。

### RAG 版本差异（重要）

当前版本对 `v1/v2` 的 RAG 策略是分开的：

- `v1`：严格单库，仅允许默认库 `default`
  - API 层会拒绝 `rag_ids`
  - API 层会拒绝 `rag_id != default`
  - 运行时工具路径也不会走多库
- `v2`：支持多库
  - 支持 `rag_id` 与 `rag_ids`
  - 支持多库并查与统一重排
  - `rag_id` 会走严格规范化校验；规范化后若等同 `default` 且原值不是显式 `default`，会返回 400

`retrieve_docs` 当前除了 `top_k`，还支持：

- `min_score` 最小分数过滤
- `rerank` 轻量重排
- `fetch_k` 重排前的候选召回数量

当前导入支持的文件类型：

- `.txt`
- `.md`
- `.py`
- `.pdf`
- `.docx`

当前内置文档包括：

- [agent_runtime.md](agent_runtime.md)
- [coding_workflow.md](coding_workflow.md)
- [rag_usage.md](rag_usage.md)
- [tooling.md](tooling.md)

### 如何触发 RAG

当前 `v1` 的 RAG 使用方式是：

- Agent 具备 `retrieve_docs` 能力
- 当任务明确提到 `docs`、`文档`、`知识库`、`先检索文档` 这类信号时，planner 会默认插入 `retrieve_docs`
- 但不是所有编程任务都会默认先查 RAG

当前默认会触发 RAG 的提示词通常会明确提到：

- `根据 docs`
- `根据文档`
- `先查文档`
- `先检索知识库`
- `按文档约定实现`

例如：

```text
根据 docs 里的约定，新增一个字符串工具类，包含 trim 和 isBlank 方法。
```

```text
请先检索相关文档，再根据文档约定实现这个功能。
```

如果你的任务本身没有明确提到文档，例如：

```text
增加一个处理日期的函数
```

那么 Agent 可能会直接根据已有上下文和代码风格回答，不一定会主动走 `retrieve_docs`。

如果你希望稳定使用 RAG，建议在提示词中显式写出：

- `先查 docs`
- `先检索文档`
- `先根据知识库内容`
- `根据导入的文档约定`

推荐写法：

```text
先检索相关文档，再根据 docs 里的约定实现一个日期处理工具类。
```

```text
请先使用文档检索工具查找相关说明，再生成代码。
```

## 5. FastAPI 服务

启动服务：

```bash
.venv/bin/uvicorn app.api.server:app --host 127.0.0.1 --port 8000
```

Swagger 文档地址：

```text
http://127.0.0.1:8000/docs
```

运行一次 Agent：

```bash
curl -s http://127.0.0.1:8000/agent/run \
  -H 'Content-Type: application/json' \
  -d '{
    "task": "解释一下这个类的作用",
    "version": "v1",
    "workdir": "/Users/tony/PycharmProjects/local_ai_inference_platform",
    "reasoning_mode": "medium",
    "model": "your-model",
    "base_url": "http://127.0.0.1:8000/v1",
    "service_token": "your-service-token",
    "max_steps": 5,
    "run_timeout_seconds": 180,
    "include_trace": true
  }'
```

查询某次运行的 trace：

```bash
curl -s http://127.0.0.1:8000/debug/traces/<run_id>
```

列出 RAG 库（供 `/rag` 列表页）：

```bash
curl -s http://127.0.0.1:8000/debug/rag/collections
```

创建空 RAG 库（供 v2 选库）：

```bash
curl -s http://127.0.0.1:8000/debug/rag/collections \
  -H 'Content-Type: application/json' \
  -d '{
    "rag_id": "product-docs"
  }'
```

列出最近运行（含 `v1/v2` 顶层记录，供 Web UI 历史页）：

```bash
curl -s 'http://127.0.0.1:8000/debug/runs?limit=50&offset=0'
```

在线更新全局 LLM 配置（概况页同源接口）：

```bash
curl -s http://127.0.0.1:8000/debug/settings/llm \
  -H 'Content-Type: application/json' \
  -d '{
    "llm_base_url": "http://127.0.0.1:8000/v1",
    "llm_model": "your-model"
  }'
```

说明：

- 更新后立即对后续运行生效
- 同时会写入项目根目录 `.env`，重启后仍保留

### 5.1 Web UI（V2 演示，可选）

仓库内提供了最小 `Vue3 + Vite` 页面，用于在浏览器里提交 `v2` 任务并查看回放与 Trace。开发服务器会把 `/agent` 与 `/debug` 代理到本机 `8000` 上的 FastAPI，因此**请先按上文启动 `uvicorn`**，再启动前端。

```bash
cd webui
npm install
npm run dev
```

或在仓库根目录直接执行（脚本会先 `npm install` 再启动 Vite）：

```bash
./webui/start.sh
```

**推荐（一次起全栈）**：若尚未开 `uvicorn`，可直接在仓库根目录执行；脚本会在需要时后台拉起 API，再启动 Vite，避免仅开前端时 `/agent/run` 代理报 `ECONNREFUSED`：

```bash
./run-all.sh
```

传给 Vite 的额外参数会原样透传，例如指定监听地址：

```bash
./webui/start.sh -- --host 127.0.0.1 --port 5173
```

然后打开终端提示的本地地址（默认 `http://127.0.0.1:5173`）。`POST /agent/run` 的鉴权仍由后端读取环境变量或请求体；若你未在浏览器里传 `api_key` / `service_token`，请保证服务端已配置 `LLM_API_KEY` 或 `LLM_SERVICE_TOKEN`。

当前页面已覆盖常用调试流程，包含：

- `/overview`：系统概况、LLM 配置查看与在线更新
- `/run`：新建运行（`v1/v2`、`max_steps`、`run_timeout_seconds`）
- `/history`：历史分页、筛选、删除与回放入口
- `/agents`：只读智能体列表
- `/rag`：RAG 列表页（创建知识库、进入详情）
- `/rag/:ragId`：RAG 详情页（该库概览、上传导入、重建索引、删除分块）
- `/runs/:runId`：执行详情、运行摘要、流程可视化与节点摘要
- `/runs/:runId/trace`：Trace 时间线

前端与后端关系：

- 依赖 `/agent` 与 `/debug` 同源路径
- 开发态通过 Vite proxy 转发到 `127.0.0.1:8000`

生产构建：

```bash
cd webui
npm run build
# 产物在 webui/dist/
```

注意：当前产物**不能直接丢给任意纯静态托管**就工作。要么：

- 让静态资源和 FastAPI 部署在同一域名/同一路径前缀下
- 要么在前面加反向代理，把 `/agent`、`/debug`、`/healthz` 转发到 FastAPI

如果只是单独打开静态文件或部署到没有 API 代理的静态站点，页面请求会失败。

## 6. Trace 查看

除了通过 API 查询，也可以直接用脚本查看时间线：

```bash
.venv/bin/python scripts/view_trace.py <run_id>
```

## 7. Coding Demo

生成演示工作区：

```bash
.venv/bin/python scripts/setup_coding_demo.py
```

生成后会得到 `demo_workspace/`，其中包含几类小范围编程任务：

- 新建 `StringUtils`
- 为 `TodoService` 增加 CRUD 方法
- 参考 `OrderService` 仿写 `ProductService`
- 修复简单测试

你可以用下面的命令验证 demo：

```bash
.venv/bin/pytest demo_workspace/tests/test_string_utils.py
.venv/bin/pytest demo_workspace/tests/test_todo_service.py
.venv/bin/pytest demo_workspace/tests/test_product_service.py
.venv/bin/pytest demo_workspace/tests/test_math_utils.py
```

如果你想按固定场景做能力演示，而不是自由提问，建议直接复用本节给出的 3 个演示任务。

其中整理了 3 个适合当前 `v1` 的演示脚本：

- 搜索 TODO 并总结
- 根据 docs 写简单工具类
- 运行测试并修复一个小问题

当前 `v1` 对“新增函数 / 工具类”这类任务，已经具备一条更稳的落盘路径：

1. 先查看项目结构
2. 再搜索现有代码模式
3. 让模型优先输出相对路径和完整代码块，例如 `path: app/utils/date_utils.py` 加 fenced code block
4. runtime 再直接调用 `write_file` 落盘

这条链路的目标是减少“模型只输出代码文本，但没有真正写文件”的情况。
如果模型没有给出可解析的路径和代码内容，则仍可能停留在文本建议阶段。
在真正执行 `write_file` 之前，runtime 还会做最小内容完整性校验；例如 Python 文件会先做语法校验，明显未闭合的三引号字符串或疑似半截结尾也会被拦住。
如果你更看重演示时“尽量先写进去”，可以在 `.env` 中设置：

```env
WRITE_VALIDATION_MODE=permissive
```

可选值说明：

- `strict`
  - 默认值
  - 内容疑似截断或 Python 语法不通过时拒绝落盘
- `permissive`
  - 只要 runtime 提取到了 `path + content`，就允许继续写入
  - 更适合演示成功率优先的场景，但落盘内容需要你后续人工检查

同时，只有当 `write_file` 真实返回成功并且目标文件确实存在时，最终总结才允许表述为“已完成写入”；否则会明确提示“仅生成了候选实现，未成功落盘”。

对于“分析项目目录结构”这类任务，当前 `v1` 还额外收紧了总结步骤：

1. 先通过工具拿到真实目录和关键配置文件
2. 再要求模型只基于现有结果直接收口
3. 不鼓励模型继续输出“还需要读取 README”这类下一步计划

这样可以降低不同模型在总结阶段表现差异过大的问题。

## 8. 存储说明

当前项目使用两套持久化：

- 主业务库：`.simple_code_agent.sqlite3`（或环境变量 `SQLITE_DB_PATH` 指定的单文件路径）
  - 保存 session、messages、runs、trace、summary、V2 workspace 等
- 若仓库根目录仍遗留旧路径 `data/app.db`，在**未**设置 `SQLITE_DB_PATH` 且主库文件尚不存在时，程序会在首次连接时**自动**将其迁移为上述统一主库
- 向量库：`.chroma/chroma.sqlite3`（不随主库环境变量变化）
  - 保存 RAG 检索所需的向量数据

## 9. 日志说明

项目默认输出统一的控制台日志，格式包含：

- 时间
- 级别
- 模块名
- `run_id`
- `session_id`
- 日志消息

同时，日志会写入项目根目录下的：

```text
logs/app.log
```

文件日志按天切分，并默认保留最近 30 天。

示例：

```text
2026-04-10 21:00:00 | INFO | app.v1.runtime.loop | run_id=... | session_id=demo-session | Starting agent loop: model=...
2026-04-10 21:00:01 | INFO | app.llm.client | run_id=... | session_id=demo-session | Sending LLM request: model=... endpoint=...
2026-04-10 21:00:30 | ERROR | app.llm.client | run_id=... | session_id=demo-session | LLM provider connection failed: error=timed out
```

你可以通过 `LOG_LEVEL` 控制输出详细程度，例如：

```env
LOG_LEVEL=INFO
```

## 10. Web UI 操作提示

### 10.1 运行超时

`/run` 页支持 `运行超时（秒）`：

- `v1`：透传到单 Agent runtime 的 `run_timeout_seconds`
- `v2`：达到超时时间后，编排器会主动停止并返回失败原因

### 10.2 执行详情中的工作目录

`/runs/:runId` 的运行摘要会展示 `workdir`：

- 新产生的 run 会持久化该字段
- 历史旧 run 可能显示 `—`（创建时未写入）

## 11. 常见问题

### 1. 为什么连续两次 CLI 运行，`run_id` 不一样？

这是正常的。

- `run_id` 表示一次具体执行
- `session_id` 表示同一个会话上下文

每次运行都会生成新的 `run_id`，只有在 `session_id` 相同的情况下，前后两次对话才会共享历史。

### 2. 为什么连续两次 CLI 运行，`session_id` 也不一样？

通常是因为你没有显式指定会话，也没有在环境变量中配置 `SESSION_ID`。

优先级如下：

1. `--session-id`
2. 当前 shell 中导出的 `SESSION_ID`
3. `.env` 中配置的 `SESSION_ID`
4. 若都没有，则自动生成新的 `session_id`

### 3. 为什么本地推理平台已经收到请求，但 CLI 仍然显示超时？

这通常表示：

- 请求已经成功发送到模型服务
- 但模型没有在 `LLM_TIMEOUT` 指定的时间内返回完整响应

这种情况常见于：

- 模型较大，首次加载较慢
- 本地推理平台正在冷启动
- 当前机器资源紧张

可以优先尝试：

- 增大 `LLM_TIMEOUT`
- 换一个更轻量的模型做对照
- 先用 `curl` 直接调用 `/v1/chat/completions` 测一下真实耗时


## 12. 当前限制

- 当前默认 Provider 是 OpenAI-compatible 协议
- streaming API 还没有接入
- 当前文档以本地开发与演示为主，不是生产部署手册
