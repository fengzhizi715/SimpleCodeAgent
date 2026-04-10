# 使用说明

本文档用于说明如何在本地运行和演示 `Simple Code Agent` 的 `v1` 版本。

如果你准备继续维护项目实现，而不是只做使用验证，建议同时阅读：

- [architecture.md](/Users/tony/PycharmProjects/SimpleCodeAgent/docs/architecture.md)
- [AGENTS.md](/Users/tony/PycharmProjects/SimpleCodeAgent/AGENTS.md)

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
WORKSPACE_ROOT=/absolute/path/to/your/project
```

如果你接的是 `local_ai_inference_platform`，推荐直接使用 `service token` 鉴权，而不是 Bearer API Key。

推荐配置说明：

- `LLM_BASE_URL` 使用 `http://127.0.0.1:8000/v1`
- `LLM_AUTH_MODE` 使用 `service_token`
- `LLM_SERVICE_TOKEN` 使用你申请好的服务令牌
- `SESSION_ID` 可以固定成一个演示会话名，方便连续提问
- `WORKSPACE_ROOT` 可以固定成你要分析的本地项目根目录

## 2. CLI 使用

最小调用：

```bash
.venv/bin/python scripts/run_cli.py "解释一下这个类的作用" \
  --version v1 \
  --model your-model \
  --base-url http://127.0.0.1:8000/v1 \
  --service-token your-service-token
```

分析其他本地项目时，可以显式指定目标目录：

```bash
.venv/bin/python scripts/run_cli.py "帮我分析这个项目的目录结构" \
  --version v1 \
  --project-root /Users/tony/PycharmProjects/local_ai_inference_platform
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

打印简版 trace：

```bash
.venv/bin/python scripts/run_cli.py "解释一下这个类的作用" \
  --version v1 \
  --trace
```

`v2` 入口已经预留，但当前还没有实现：

```bash
.venv/bin/python scripts/run_cli.py "hello" --version v2
```

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

导入完成后，Agent 在执行过程中可以通过 `retrieve_docs` 工具检索这些文档片段。

当前内置文档包括：

- [agent_runtime.md](agent_runtime.md)
- [coding_workflow.md](coding_workflow.md)
- [rag_usage.md](rag_usage.md)
- [tooling.md](tooling.md)

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
    "model": "your-model",
    "base_url": "http://127.0.0.1:8000/v1",
    "service_token": "your-service-token",
    "include_trace": true
  }'
```

查询某次运行的 trace：

```bash
curl -s http://127.0.0.1:8000/debug/traces/<run_id>
```

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

## 8. 存储说明

当前项目使用两套持久化：

- 主业务库：[.simple_code_agent.sqlite3](/Users/tony/PycharmProjects/SimpleCodeAgent/.simple_code_agent.sqlite3)
  - 保存 session、messages、runs、trace、summary
- 向量库：[.chroma/chroma.sqlite3](/Users/tony/PycharmProjects/SimpleCodeAgent/.chroma/chroma.sqlite3)
  - 保存 RAG 检索所需的向量数据

## 9. 当前限制

- `v2` 还没有正式实现
- 当前默认 Provider 是 OpenAI-compatible 协议
- streaming API 还没有接入
- 当前文档以本地开发与演示为主，不是生产部署手册

## 10. 常见问题

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
