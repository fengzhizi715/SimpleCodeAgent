function errorMessageFromPayload(payload) {
  if (!payload || typeof payload !== "object") {
    return "请求失败";
  }
  const { detail } = payload;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (item && typeof item === "object" && "msg" in item ? String(item.msg) : JSON.stringify(item)))
      .join("；");
  }
  if (detail && typeof detail === "object") {
    return JSON.stringify(detail);
  }
  return "请求失败";
}

const BACKEND_HINT =
  "请先在仓库根目录另开终端启动 API（默认 8000 端口）：\n" +
  "  .venv/bin/uvicorn app.api.server:app --host 127.0.0.1 --port 8000\n" +
  "启动后本页再重试。详见 docs/usage_guide.md §5。";

async function requestJson(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    });
  } catch (err) {
    const raw = err instanceof Error ? err.message : String(err);
    throw new Error(`无法连接后端（${raw}）。\n${BACKEND_HINT}`);
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(errorMessageFromPayload(payload));
  }
  return payload;
}

export async function runAgent(input) {
  return requestJson("/agent/run", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function getRunReplay(runId) {
  return requestJson(`/debug/v2/runs/${encodeURIComponent(runId)}/replay`);
}

export async function listV2Runs({ limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return requestJson(`/debug/v2/runs?${params.toString()}`);
}
