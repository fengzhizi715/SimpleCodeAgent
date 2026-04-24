#!/usr/bin/env bash
# 一键：在本机 8000 启动 FastAPI（若尚未运行），再启动 Web UI（Vite 5173）。
# 解决「仅开 webui 时 /agent/run 代理 ECONNREFUSED」问题。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"

UVICORN="${ROOT_DIR}/.venv/bin/uvicorn"
if [[ ! -x "${UVICORN}" ]]; then
  echo "错误：未找到 ${UVICORN}，请先创建虚拟环境并 pip install -r requirements.txt" >&2
  exit 1
fi

API_URL="http://127.0.0.1:8000/healthz"
STARTED_API=0
UV_PID=""

cleanup() {
  if [[ "${STARTED_API}" -eq 1 && -n "${UV_PID}" ]]; then
    echo "" >&2
    echo "正在停止本脚本启动的 uvicorn (pid=${UV_PID})…" >&2
    kill "${UV_PID}" 2>/dev/null || true
    wait "${UV_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

if curl -sSf -m 2 "${API_URL}" >/dev/null 2>&1; then
  echo "已检测到 ${API_URL}，跳过启动 uvicorn。"
else
  echo "未检测到 API，正在后台启动: uvicorn app.api.server:app --host 127.0.0.1 --port 8000"
  "${UVICORN}" app.api.server:app --host 127.0.0.1 --port 8000 &
  UV_PID=$!
  STARTED_API=1
  ok=0
  for _ in $(seq 1 60); do
    if curl -sSf -m 2 "${API_URL}" >/dev/null 2>&1; then
      ok=1
      break
    fi
    sleep 0.25
  done
  if [[ "${ok}" -ne 1 ]]; then
    echo "错误：等待 API 就绪超时。请检查 8000 端口是否被占用、或查看 uvicorn 报错。" >&2
    exit 1
  fi
  echo "API 已就绪: ${API_URL}"
fi

cd "${ROOT_DIR}/webui"
if [[ ! -d node_modules ]]; then
  echo "首次运行，正在 npm install…"
  npm install
fi
echo "启动 Vite: http://127.0.0.1:5173 （Ctrl+C 结束；由本脚本拉起的 uvicorn 会随脚本退出而停止）"
# 注意：不可使用 exec，否则无法在本进程退出时 trap 掉后台 uvicorn
npm run dev -- "$@"
