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
  api/
  contracts/
  core/
  db/
  llm/
  trace/
  v1/
    memory/
    planner/
    rag/
    runtime/
    tools/
  v2/
docs/
scripts/
demo_workspace/
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

- [docs/usage_guide.md](/Users/tony/PycharmProjects/SimpleCodeAgent/docs/usage_guide.md)

其中包含：

- CLI 用法
- RAG 文档导入
- FastAPI 调用方式
- Trace 查看
- Coding demo 演示流程

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
