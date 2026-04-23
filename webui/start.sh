#!/usr/bin/env bash
# 启动 Web UI 开发服务器（Vite）。请先在本机 8000 端口启动 FastAPI，见 docs/usage_guide.md。
set -euo pipefail

WEBUI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${WEBUI_DIR}"

if ! command -v npm >/dev/null 2>&1; then
  echo "错误：未找到 npm，请先安装 Node.js（建议 LTS）。" >&2
  exit 1
fi

echo "安装/同步依赖（webui）…"
npm install

if ! curl -sS -o /dev/null -m 2 --fail "http://127.0.0.1:8000/healthz" 2>/dev/null; then
  echo "" >&2
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2
  echo "  提示：本机 8000 端口未检测到 FastAPI（/healthz 无响应）。" >&2
  echo "  Web UI 会把 /agent、/debug 代理到 127.0.0.1:8000，需先启动后端：" >&2
  echo "    cd \"$(cd \"${WEBUI_DIR}/..\" && pwd)\" && .venv/bin/uvicorn app.api.server:app --host 127.0.0.1 --port 8000" >&2
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2
  echo "" >&2
fi

echo "启动 Vite 开发服务器…"
exec npm run dev -- "$@"
