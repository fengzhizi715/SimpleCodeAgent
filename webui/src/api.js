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

export async function updateLLMSettings(input) {
  return requestJson("/debug/settings/llm", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function validateLLMSettings() {
  return requestJson("/debug/settings/llm/validate", {
    method: "POST",
  });
}

export async function runAgent(input) {
  return requestJson("/run", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function getRunReplay(runId) {
  return requestJson(`/debug/v2/runs/${encodeURIComponent(runId)}/replay`);
}

export async function getRunDetail(runId) {
  return requestJson(`/debug/runs/${encodeURIComponent(runId)}/detail`);
}

export async function getRunTrace(runId) {
  return requestJson(`/debug/traces/${encodeURIComponent(runId)}`);
}

export async function getV3EventChain(runId, { executionChainId = "", eventId = "" } = {}) {
  const params = new URLSearchParams();
  if (executionChainId) {
    params.set("execution_chain_id", String(executionChainId));
  }
  if (eventId) {
    params.set("event_id", String(eventId));
  }
  const query = params.toString();
  return requestJson(`/debug/v3/runs/${encodeURIComponent(runId)}/event-chain${query ? `?${query}` : ""}`);
}

export async function getV3EventChainView(runId, { executionChainId = "", eventId = "" } = {}) {
  const params = new URLSearchParams();
  if (executionChainId) {
    params.set("execution_chain_id", String(executionChainId));
  }
  if (eventId) {
    params.set("event_id", String(eventId));
  }
  const query = params.toString();
  let response;
  try {
    response = await fetch(`/debug/v3/runs/${encodeURIComponent(runId)}/event-chain/view${query ? `?${query}` : ""}`);
  } catch (err) {
    const raw = err instanceof Error ? err.message : String(err);
    throw new Error(`无法连接后端（${raw}）。\n${BACKEND_HINT}`);
  }
  const text = await response.text();
  if (!response.ok) {
    throw new Error(text || "请求失败");
  }
  return text;
}

export async function replayV3EventChain(runId, { eventId = "" } = {}) {
  const params = new URLSearchParams();
  if (eventId) {
    params.set("event_id", String(eventId));
  }
  return requestJson(`/debug/v3/runs/${encodeURIComponent(runId)}/event-chain/replay?${params.toString()}`, {
    method: "POST",
  });
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

export async function listAgents() {
  return requestJson("/debug/agents");
}

export async function getUsageSummary({ recentLimit = 20 } = {}) {
  const params = new URLSearchParams({
    recent_limit: String(recentLimit),
  });
  return requestJson(`/debug/usage/summary?${params.toString()}`);
}

export const listV2Runs = listRuns;
export const deleteV2Run = deleteRun;

export async function getRagOverview({ limit = 20, offset = 0, ragId = "default" } = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    rag_id: String(ragId || "default"),
  });
  return requestJson(`/debug/rag/overview?${params.toString()}`);
}

export async function listRagCollections() {
  return requestJson("/debug/rag/collections");
}

export async function createRagCollection(ragId, options = {}) {
  const id = String(ragId ?? "").trim();
  const chunkSize = Number(options.chunk_size);
  const overlap = Number(options.overlap);
  return requestJson("/debug/rag/collections", {
    method: "POST",
    body: JSON.stringify({
      rag_id: id,
      ...(Number.isFinite(chunkSize) ? { chunk_size: chunkSize } : {}),
      ...(Number.isFinite(overlap) ? { overlap } : {}),
    }),
  });
}

export async function deleteRagCollection(ragId) {
  return requestJson(`/debug/rag/collections/${encodeURIComponent(ragId)}`, {
    method: "DELETE",
  });
}

export async function deleteRagSource(source, ragId = "default") {
  return requestJson("/debug/rag/delete-source", {
    method: "POST",
    body: JSON.stringify({ source, rag_id: ragId || "default" }),
  });
}

export async function reindexRagSource(source, ragId = "default") {
  return requestJson("/debug/rag/reindex-source", {
    method: "POST",
    body: JSON.stringify({ source, rag_id: ragId || "default" }),
  });
}

export async function uploadRagFile(file, sourceDir = "uploads", ragId = "default") {
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
      rag_id: ragId || "default",
    }),
  });
}
