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
    const isFormDataBody = options.body instanceof FormData;
    response = await fetch(path, {
      headers: {
        ...(isFormDataBody ? {} : { "Content-Type": "application/json" }),
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

export async function getHealthz() {
  return requestJson("/healthz");
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

export async function listRuns({ limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return requestJson(`/debug/runs?${params.toString()}`);
}

export async function deleteRun(runId) {
  return requestJson(`/debug/runs/${encodeURIComponent(runId)}`, {
    method: "DELETE",
  });
}

export const listV2Runs = listRuns;
export const deleteV2Run = deleteRun;

export async function getRagOverview({ limit = 20, offset = 0 } = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return requestJson(`/debug/rag/overview?${params.toString()}`);
}

export async function deleteRagSource(source) {
  return requestJson("/debug/rag/delete-source", {
    method: "POST",
    body: JSON.stringify({ source }),
  });
}

export async function reindexRagSource(source) {
  return requestJson("/debug/rag/reindex-source", {
    method: "POST",
    body: JSON.stringify({ source }),
  });
}

export async function uploadRagFile(file, sourceDir = "uploads") {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  const contentBase64 = btoa(binary);

  return requestJson("/debug/rag/upload", {
    method: "POST",
    body: JSON.stringify({
      filename: file.name,
      source_dir: sourceDir,
      content_base64: contentBase64,
    }),
  });
}
