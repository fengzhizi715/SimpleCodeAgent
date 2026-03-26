# 使用说明

本文档用于说明如何在本地运行和演示 `Simple Code Agent` 的 `v1` 版本。

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
LLM_BASE_URL=http://localhost:8000/v1
LLM_API_KEY=your-key
LLM_MODEL=your-model
```

## 2. CLI 使用

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

## 4. RAG 文档导入

先导入 `docs/` 目录下的示例文档：

```bash
.venv/bin/python scripts/ingest_docs.py --docs-dir docs
```

导入完成后，Agent 在执行过程中可以通过 `retrieve_docs` 工具检索这些文档片段。

当前内置文档包括：

- [agent_runtime.md](/Users/tony/PycharmProjects/SimpleCodeAgent/docs/agent_runtime.md)
- [coding_workflow.md](/Users/tony/PycharmProjects/SimpleCodeAgent/docs/coding_workflow.md)
- [rag_usage.md](/Users/tony/PycharmProjects/SimpleCodeAgent/docs/rag_usage.md)
- [tooling.md](/Users/tony/PycharmProjects/SimpleCodeAgent/docs/tooling.md)

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
    "base_url": "http://localhost:8000/v1",
    "api_key": "your-key",
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
