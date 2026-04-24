<template>
  <section class="panel">
    <h2>运行历史</h2>
    <p class="muted">
      当前列表展示用户发起的顶层运行（API：<code>GET /debug/runs</code>），包含 <code>v1</code> 与
      <code>v2</code>。v1 规划过程里的 direct-tool 子步骤会默认隐藏，避免和一次完整运行混在一起。
    </p>
    <div class="row" style="margin-bottom: 12px">
      <button class="btn-secondary" :disabled="loading" @click="load">刷新</button>
      <RouterLink to="/run">新建任务</RouterLink>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
  </section>

  <section class="panel" v-if="runs.length">
    <div class="history-table-wrap">
      <table class="history-table">
        <thead>
          <tr>
            <th>版本</th>
            <th>状态</th>
            <th>run_id</th>
            <th>目标</th>
            <th>结果摘要</th>
            <th>更新时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="r in runs" :key="r.run_id">
            <tr>
              <td>
                <span class="agent-version" :class="versionClass(r.agent_version)">{{ formatVersion(r.agent_version) }}</span>
              </td>
              <td>
                <span class="status-pill" :class="statusClass(r.status)">{{ r.status || "unknown" }}</span>
              </td>
              <td class="mono">{{ shortId(r.run_id) }}</td>
              <td class="history-task" :title="r.user_goal || r.task">{{ truncate(r.user_goal || r.task, 96) }}</td>
              <td class="history-output" :title="plainText(r.final_output)">{{ truncate(plainText(r.final_output), 120) }}</td>
              <td class="muted history-time">{{ formatDateTime(r.updated_at) }}</td>
              <td class="history-actions">
                <template v-if="normalizeVersion(r.agent_version) === 'v2'">
                  <RouterLink :to="{ name: 'execution', params: { runId: r.run_id } }">详情</RouterLink>
                  <RouterLink :to="{ name: 'trace', params: { runId: r.run_id } }">Trace</RouterLink>
                </template>
                <template v-else>
                  <button class="btn-secondary btn-sm" @click="toggleExpanded(r.run_id)">
                    {{ expandedRunId === r.run_id ? "收起" : "查看结果" }}
                  </button>
                </template>
                <button class="btn-danger btn-sm" :disabled="deletingRunId === r.run_id" @click="removeRun(r.run_id)">
                  {{ deletingRunId === r.run_id ? "删除中..." : "删除" }}
                </button>
              </td>
            </tr>
            <tr v-if="expandedRunId === r.run_id" class="history-expanded-row">
              <td colspan="7">
                <pre>{{ r.final_output || "暂无结果内容。" }}</pre>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
    <div class="row" style="margin-top: 12px; justify-content: space-between">
      <div class="row">
        <label style="margin-bottom: 0">每页</label>
        <select v-model.number="pageSize" @change="onPageSizeChange">
          <option :value="10">10</option>
          <option :value="20">20</option>
          <option :value="50">50</option>
        </select>
      </div>
      <div class="row">
        <span class="muted">第 {{ currentPage }} / {{ totalPages }} 页，共 {{ total }} 条</span>
        <button class="btn-secondary" :disabled="currentPage <= 1 || loading" @click="goPrevPage">上一页</button>
        <button class="btn-secondary" :disabled="currentPage >= totalPages || loading" @click="goNextPage">
          下一页
        </button>
      </div>
    </div>
  </section>
  <section v-else-if="!loading && !error" class="panel muted">暂无历史记录。</section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { deleteRun, listRuns } from "../api";

const runs = ref([]);
const loading = ref(false);
const error = ref("");
const deletingRunId = ref("");
const total = ref(0);
const pageSize = ref(20);
const page = ref(1);
const expandedRunId = ref("");

function shortId(id) {
  if (!id || id.length <= 12) return id;
  return `${id.slice(0, 8)}…`;
}

function truncate(s, n) {
  if (!s) return "";
  return s.length <= n ? s : `${s.slice(0, n)}…`;
}

function plainText(s) {
  if (!s) return "";
  return String(s).replace(/\s+/g, " ").trim();
}

function formatDateTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function normalizeVersion(v) {
  if (!v || typeof v !== "string") return "v2";
  const s = v.trim().toLowerCase();
  if (s === "v1" || s === "v2" || s === "v3") return s;
  if (s.startsWith("v")) return s;
  return `v${s}`;
}

function formatVersion(v) {
  const n = normalizeVersion(v);
  return n.toUpperCase();
}

function versionClass(v) {
  const n = normalizeVersion(v);
  if (n === "v1" || n === "v2" || n === "v3") {
    return `agent-version--${n}`;
  }
  return "agent-version--future";
}

function statusClass(status) {
  const value = String(status || "").toLowerCase();
  if (value === "completed" || value === "partial_completed") return "status-pill--ok";
  if (value === "failed") return "status-pill--failed";
  return "status-pill--running";
}

async function load() {
  error.value = "";
  loading.value = true;
  try {
    const data = await listRuns({ limit: pageSize.value, offset: (page.value - 1) * pageSize.value });
    runs.value = Array.isArray(data.runs) ? data.runs : [];
    total.value = Number(data.total || 0);
    const pages = Math.max(1, Math.ceil(total.value / pageSize.value));
    if (page.value > pages) {
      page.value = pages;
      await load();
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
    runs.value = [];
    total.value = 0;
  } finally {
    loading.value = false;
  }
}

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)));
const currentPage = computed(() => page.value);

async function goPrevPage() {
  if (page.value <= 1) return;
  page.value -= 1;
  await load();
}

async function goNextPage() {
  if (page.value >= totalPages.value) return;
  page.value += 1;
  await load();
}

async function onPageSizeChange() {
  page.value = 1;
  await load();
}

async function removeRun(runId) {
  if (!runId) return;
  const ok = window.confirm(`确认删除 run ${shortId(runId)} 吗？该记录关联的 replay/trace 将一并删除。`);
  if (!ok) return;
  deletingRunId.value = runId;
  error.value = "";
  try {
    await deleteRun(runId);
    if (expandedRunId.value === runId) {
      expandedRunId.value = "";
    }
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "删除失败";
  } finally {
    deletingRunId.value = "";
  }
}

function toggleExpanded(runId) {
  expandedRunId.value = expandedRunId.value === runId ? "" : runId;
}

onMounted(load);
</script>

<style scoped>
.mono {
  font-family: var(--font-mono);
  font-size: 0.8125rem;
}

.history-table-wrap {
  overflow-x: auto;
}

.history-table {
  min-width: 980px;
}

.history-task,
.history-output {
  max-width: 280px;
}

.history-output {
  color: var(--text-secondary);
}

.history-time {
  white-space: nowrap;
}

.history-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  white-space: nowrap;
}

.history-expanded-row td {
  background: #f8f9fb;
  padding: 0;
}

.history-expanded-row pre {
  margin: 0;
  border-radius: 0;
  max-height: 420px;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 3px 9px;
  font-size: 0.72rem;
  font-weight: 700;
  border: 1px solid transparent;
}

.status-pill--ok {
  background: rgba(22, 163, 74, 0.12);
  color: #15803d;
  border-color: rgba(22, 163, 74, 0.22);
}

.status-pill--failed {
  background: rgba(220, 38, 38, 0.12);
  color: #b91c1c;
  border-color: rgba(220, 38, 38, 0.22);
}

.status-pill--running {
  background: #eef0f4;
  color: var(--text-secondary);
  border-color: var(--border-subtle);
}
</style>
