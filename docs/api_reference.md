# API Reference

本文档整理 SimpleCodeAgent 当前对外暴露的 HTTP API。

默认服务地址：

```text
http://127.0.0.1:8000
```

启动示例：

```bash
.venv/bin/uvicorn app.api.server:app --host 127.0.0.1 --port 8000
```

说明：

- `v1` 是单 Agent Runtime，只支持默认 RAG 知识库。
- `v2` 是中心化多 Agent Runtime，支持运行级 Agent 配置、多 RAG、Reviewer 策略等。
- `/debug/*` 当前主要服务 WebUI、课程演示与本地调试，生产化前应增加鉴权与权限控制。

## 目录

- [1. 运行 Agent](#1-运行-agent)
- [2. 健康检查与配置](#2-健康检查与配置)
- [3. Trace 与运行历史](#3-trace-与运行历史)
- [4. Agent Catalog](#4-agent-catalog)
- [5. RAG 管理](#5-rag-管理)
- [6. 常见错误](#6-常见错误)
- [7. OpenAPI](#7-openapi)

## 1. 运行 Agent

### `POST /agent/run`

执行一次 Agent 任务。

常用请求体：

```json
{
  "task": "帮我分析这个项目的目录结构",
  "version": "v2",
  "workdir": "/path/to/project",
  "model": "your-model-name",
  "max_steps": 5,
  "include_trace": false
}
```

主要字段：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `task` | string | 必填 | 用户目标 |
| `version` | `v1` / `v2` | `v1` | 运行版本 |
| `session_id` | string | 自动生成 | 会话 ID；会按项目派生 |
| `workdir` | string | 配置默认值 | 目标项目目录 |
| `project_root` | string | null | 历史兼容字段，等价于 `workdir` |
| `model` | string | `LLM_MODEL` | 覆盖模型名 |
| `base_url` | string | `LLM_BASE_URL` | 覆盖 LLM Base URL |
| `api_key` | string | 环境配置 | 覆盖 API Key |
| `service_token` | string | 环境配置 | 覆盖 Service Token |
| `system_prompt` | string | `You are a helpful assistant.` | v1 系统提示词 |
| `temperature` | number | `0.0` | 采样温度 |
| `reasoning_mode` | `default` / `low` / `medium` / `high` | `default` | 推理模式标记 |
| `max_steps` | integer | `3` | 最大执行步数，范围 `1-20` |
| `run_timeout_seconds` | integer | `120` | 单次运行超时时间，范围 `1-600` |
| `include_trace` | boolean | `false` | 是否在响应中附带 trace |

V2 专属字段：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `v2_enabled_agents` | string[] | null | 可选：`orchestrator`、`planner`、`analyst`、`coder`、`tester`、`reviewer`；`orchestrator/planner` 会强制启用 |
| `v2_review_strategy` | object | null | Reviewer 运行级策略 |
| `v2_use_rag` | boolean | `true` | 本次 V2 运行是否允许使用 RAG |
| `rag_id` | string | null | 单个知识库 ID |
| `rag_ids` | string[] | null | 多知识库并查 |

`v2_review_strategy` 示例：

```json
{
  "llm_enabled": true,
  "strictness": "normal",
  "max_issues": 5,
  "focus_areas": ["security", "tests"],
  "rule_groups": ["scope", "testing", "security", "maintainability", "boundaries", "api", "domain"],
  "test_failure_mode": "block"
}
```

响应示例：

```json
{
  "answer": "目标：帮我分析这个项目的目录结构...",
  "version": "v2",
  "run_id": "e47bd18c-997e-4914-99d9-f1d6c4d300ef",
  "session_id": "demo-session@project",
  "reasoning_mode": "default",
  "status": "completed",
  "step_count": 4,
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  },
  "metrics": {
    "duration_seconds": 12.3,
    "llm_calls": 1,
    "tool_calls": 3,
    "tool_errors": 0,
    "memory_writes": 0,
    "fallbacks": 0
  },
  "trace": []
}
```

约束：

- `v1` 不支持 `rag_ids`。
- `v1` 只支持默认知识库 `default`。
- 如果未传 `model`，需要配置 `LLM_MODEL`。
- 如果未传鉴权字段，需要配置 `LLM_API_KEY` 或 `LLM_SERVICE_TOKEN`。

## 2. 健康检查与配置

### `GET /healthz`

查询服务健康状态和当前 LLM 配置。

响应：

```json
{
  "status": "ok",
  "app_name": "SimpleCodeAgent",
  "env": "dev",
  "llm_base_url": "http://127.0.0.1:8000/v1",
  "llm_model": "your-model"
}
```

### `POST /debug/settings/llm`

更新全局 `LLM_BASE_URL` / `LLM_MODEL`，会立即生效并写入 `.env`。

请求：

```json
{
  "llm_base_url": "http://127.0.0.1:8000/v1",
  "llm_model": "your-model"
}
```

响应同 `/healthz`。

## 3. Trace 与运行历史

### `GET /debug/traces/{run_id}`

按 `run_id` 查询 Trace 时间线。v1/v2 顶层 run 都可使用。

响应：

```json
{
  "run_id": "run-id",
  "events": [
    {
      "id": "event-id",
      "run_id": "run-id",
      "root_run_id": "root-run-id",
      "session_id": "session-id",
      "actor": "orchestrator",
      "action": "run",
      "status": "started",
      "event_type": "run_started",
      "message": "V2 orchestrator run started.",
      "payload": {}
    }
  ]
}
```

### `GET /debug/traces-root/{root_run_id}`

按 `root_run_id` 查询整棵运行树的 Trace，适合查看父子 run 关系。

### `GET /debug/runs`

查询运行历史列表，默认隐藏 v1 planner/direct-tool 内部子 run。

Query 参数：

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `limit` | integer | `50` | 返回条数，范围 `1-200` |
| `offset` | integer | `0` | 分页偏移 |

响应：

```json
{
  "total": 1,
  "limit": 50,
  "offset": 0,
  "runs": [
    {
      "run_id": "run-id",
      "session_id": "session-id",
      "model": "model",
      "task": "用户目标",
      "agent_version": "v2",
      "status": "completed",
      "step_count": 4,
      "final_output": "最终输出",
      "created_at": "2026-04-28T00:00:00",
      "updated_at": "2026-04-28T00:00:10",
      "user_goal": "用户目标"
    }
  ]
}
```

### `GET /debug/v2/runs`

兼容旧路径，当前行为与 `/debug/runs` 一致。

### `DELETE /debug/runs/{run_id}`

删除单条 run 及其关联回放数据。

响应：

```json
{
  "run_id": "run-id",
  "deleted": true
}
```

### `DELETE /debug/v2/runs/{run_id}`

兼容旧路径，当前行为与 `/debug/runs/{run_id}` 一致。

### `GET /debug/v2/runs/{run_id}/replay`

查询 V2 单次运行回放视图。

响应包含：

- `run`
- `workspace`
- `delegations`
- `artifacts`
- `trace`
- `execution_log`
- `delegation_tree`
- `execution_nodes`
- `teaching_view`

### `GET /debug/v2/sessions/{session_id}/replay`

查询 V2 session 聚合回放视图。

## 4. Agent Catalog

### `GET /debug/agents`

列出当前 V2 Runtime 注册的智能体。

响应：

```json
{
  "total": 5,
  "agents": [
    {
      "agent_id": "planner",
      "role": "planner",
      "description": "Generate structured plans.",
      "capabilities": ["planning", "replan"],
      "availability": "enabled"
    }
  ]
}
```

## 5. RAG 管理

### `GET /debug/rag/collections`

查询当前可用 RAG 知识库列表。

响应：

```json
{
  "total": 2,
  "items": [
    {
      "rag_id": "default",
      "collection_name": "codeagent_docs"
    },
    {
      "rag_id": "product-docs",
      "collection_name": "codeagent_docs__product-docs"
    }
  ]
}
```

### `POST /debug/rag/collections`

创建空 RAG 知识库；若已存在则幂等。当前支持保存每个知识库的 `chunk_size / overlap`。

请求：

```json
{
  "rag_id": "product-docs",
  "chunk_size": 800,
  "overlap": 120
}
```

响应：

```json
{
  "rag_id": "product-docs",
  "collection_name": "codeagent_docs__product-docs",
  "chunk_size": 800,
  "overlap": 120
}
```

约束：

- `rag_id` 会规范化为小写。
- `overlap` 必须小于 `chunk_size`。
- `chunk_size` 范围：`100-8000`。
- `overlap` 范围：`0-4000`。

### `DELETE /debug/rag/collections/{rag_id}`

删除非默认 RAG 知识库及其切分配置。

响应：

```json
{
  "rag_id": "product-docs",
  "collection_name": "codeagent_docs__product-docs",
  "config_deleted": true
}
```

约束：

- `default` 知识库不允许删除。

### `GET /debug/rag/overview`

查询指定 RAG 知识库概览。

Query 参数：

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `rag_id` | string | `default` | 知识库 ID |
| `limit` | integer | `20` | 文件分页大小，范围 `1-200` |
| `offset` | integer | `0` | 文件分页偏移 |

响应：

```json
{
  "backend": "chroma",
  "rag_id": "default",
  "collection_name": "codeagent_docs",
  "persist_dir": ".chroma",
  "embedding_provider": "local-hash",
  "embedding_model": "local-hash",
  "embedding_base_url": "",
  "chunk_size": 800,
  "overlap": 120,
  "total_chunks": 10,
  "file_count": 2,
  "limit": 20,
  "offset": 0,
  "sampled_chunk_count": 10,
  "files": [
    {
      "source": "docs/example.md",
      "chunk_count": 5
    }
  ]
}
```

### `POST /debug/rag/upload`

上传单个文件并导入指定 RAG 知识库。文件会写入仓库 `docs/{source_dir}` 下。

请求：

```json
{
  "filename": "guide.md",
  "content_base64": "IyBIZWxsbyBSQUc=",
  "source_dir": "uploads",
  "rag_id": "product-docs"
}
```

响应：

```json
{
  "source": "docs/uploads/guide.md",
  "rag_id": "product-docs",
  "ingested_chunks": 3
}
```

说明：

- `source_dir` 必须位于仓库 `docs` 目录内。
- 导入时会读取该 `rag_id` 保存的 `chunk_size / overlap`。
- 当前支持文件类型：`.txt`、`.md`、`.py`、`.pdf`、`.docx`。

### `POST /debug/rag/delete-source`

从指定 RAG 知识库中删除某个 source 的全部分块。

请求：

```json
{
  "source": "docs/uploads/guide.md",
  "rag_id": "product-docs"
}
```

响应：

```json
{
  "source": "docs/uploads/guide.md",
  "rag_id": "product-docs",
  "deleted_chunks": 3
}
```

### `POST /debug/rag/reindex-source`

删除某个 source 的旧分块并重新导入。

请求：

```json
{
  "source": "docs/uploads/guide.md",
  "rag_id": "product-docs"
}
```

响应：

```json
{
  "source": "docs/uploads/guide.md",
  "rag_id": "product-docs",
  "deleted_chunks": 3,
  "ingested_chunks": 4
}
```

说明：

- `source` 必须位于仓库目录内。
- 重建时会读取该 `rag_id` 保存的 `chunk_size / overlap`。

## 6. 常见错误

| HTTP 状态码 | 场景 |
| --- | --- |
| `400` | 参数非法、缺少模型名、缺少鉴权、RAG ID 非法、v1 使用多 RAG |
| `404` | run / trace / replay / source / RAG collection 不存在 |
| `500` | Agent Runtime、LLM Provider、RAG 导入等内部错误 |

## 7. OpenAPI

FastAPI 默认还会暴露交互式文档：

```text
http://127.0.0.1:8000/docs
```

以及 OpenAPI JSON：

```text
http://127.0.0.1:8000/openapi.json
```
