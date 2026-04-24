<template>
  <section class="panel history-intro">
    <h2>运行历史</h2>
    <details class="history-intro-details">
      <summary class="history-intro-summary">关于本列表（数据来源与过滤规则）</summary>
      <p class="muted history-intro-body">
        展示用户发起的顶层运行（<code>GET /debug/runs</code>），含 <code>v1</code> / <code>v2</code>。
        v1 规划中的 direct-tool 子步骤默认不显示，避免与一次完整运行混在一起。
      </p>
    </details>
    <div class="row history-toolbar">
      <button class="btn-secondary" :disabled="loading" @click="load">
        {{ loading ? "加载中…" : "刷新" }}
      </button>
      <RouterLink to="/run">新建任务</RouterLink>
    </div>
    <div class="history-filters">
      <input v-model.trim="keyword" placeholder="搜索 task / 摘要 / run_id" />
      <select v-model="versionFilter">
        <option value="">全部版本</option>
        <option value="v1">V1</option>
        <option value="v2">V2</option>
        <option value="v3">V3</option>
      </select>
      <select v-model="statusFilter">
        <option value="">全部状态</option>
        <option value="completed">completed</option>
        <option value="failed">failed</option>
        <option value="running">running / other</option>
      </select>
      <button class="btn-secondary btn-sm" type="button" @click="clearFilters">清空筛选</button>
    </div>
    <div v-if="runs.length" class="history-stats">
      <span class="history-stat muted">本页筛选 <strong>{{ displayRuns.length }}</strong> / {{ runs.length }} 条</span>
      <span v-if="filterStats.completed" class="history-stat-pill history-stat-pill--ok">完成 {{ filterStats.completed }}</span>
      <span v-if="filterStats.failed" class="history-stat-pill history-stat-pill--bad">失败 {{ filterStats.failed }}</span>
      <span v-if="filterStats.other" class="history-stat-pill history-stat-pill--muted">其它 {{ filterStats.other }}</span>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
  </section>

  <Teleport to="body">
    <div v-if="copyToast" class="history-toast" role="status">{{ copyToast }}</div>
  </Teleport>

  <section v-if="runs.length" class="panel history-table-panel">
    <div class="history-table-scroll">
      <table class="history-table">
        <colgroup>
          <col style="width: 72px" />
          <col style="width: 128px" />
          <col style="width: 150px" />
          <col style="width: 30%" />
          <col style="width: 34%" />
          <col style="width: 150px" />
          <col style="width: 210px" />
        </colgroup>
        <thead>
          <tr>
            <th class="th-narrow">版本</th>
            <th class="th-narrow">状态</th>
            <th class="th-run-id">run_id</th>
            <th>目标</th>
            <th>结果摘要</th>
            <th class="th-time">更新时间</th>
            <th class="th-actions">操作</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="r in displayRuns" :key="r.run_id">
            <tr class="history-row">
              <td>
                <span class="agent-version" :class="versionClass(r.agent_version)">{{ formatVersion(r.agent_version) }}</span>
              </td>
              <td>
                <span class="status-pill" :class="statusClass(r.status)">{{ r.status || "unknown" }}</span>
              </td>
              <td
                class="mono history-run-id history-run-id--clickable"
                :title="`点击复制：${r.run_id}`"
                @click="copyRunId(r.run_id)"
              >
                {{ shortId(r.run_id) }}
              </td>
              <td class="td-target" :title="r.user_goal || r.task">
                <div class="history-cell-text history-task">{{ r.user_goal || r.task || "—" }}</div>
              </td>
              <td class="td-summary" :title="plainText(r.final_output)">
                <div class="history-cell-text history-output">{{ summaryCell(r.final_output) }}</div>
              </td>
              <td class="muted history-time td-time">{{ formatDateTimeCompact(r.updated_at) }}</td>
              <td class="history-actions td-actions">
                <div class="history-action-group">
                  <template v-if="normalizeVersion(r.agent_version) === 'v2'">
                    <RouterLink class="history-action history-action--primary" :to="{ name: 'execution', params: { runId: r.run_id } }">
                      详情
                    </RouterLink>
                    <RouterLink class="history-action" :to="{ name: 'trace', params: { runId: r.run_id } }">
                      Trace
                    </RouterLink>
                  </template>
                  <template v-else>
                    <button type="button" class="history-action history-action--primary" @click="toggleExpanded(r.run_id)">
                      {{ expandedRunId === r.run_id ? "收起" : "结果" }}
                    </button>
                  </template>
                  <button
                    type="button"
                    class="history-action history-action--danger"
                    :disabled="deletingRunId === r.run_id"
                    @click="removeRun(r.run_id)"
                  >
                    {{ deletingRunId === r.run_id ? "删除中" : "删除" }}
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="expandedRunId === r.run_id" class="history-expanded-row">
              <td colspan="7">
                <pre>{{ r.final_output || "暂无结果内容。" }}</pre>
              </td>
            </tr>
          </template>
          <tr v-if="!displayRuns.length">
            <td colspan="7" class="muted history-empty-filter">当前筛选条件下无结果，可尝试清空筛选。</td>
          </tr>
        </tbody>
      </table>
    </div>

    <footer class="history-pagination">
      <div class="row">
        <label class="history-page-label" for="history-page-size">每页</label>
        <select id="history-page-size" v-model.number="pageSize" @change="onPageSizeChange">
          <option :value="10">10</option>
          <option :value="20">20</option>
          <option :value="50">50</option>
        </select>
      </div>
      <div class="row history-pagination-right">
        <span class="muted history-page-info">
          第 <span class="history-page-current">{{ currentPage }}</span> / {{ totalPages }} 页 · 共 {{ total }} 条
        </span>
        <button class="btn-secondary btn-sm" type="button" :disabled="currentPage <= 1 || loading" @click="goPrevPage">
          上一页
        </button>
        <button class="btn-secondary btn-sm" type="button" :disabled="currentPage >= totalPages || loading" @click="goNextPage">
          下一页
        </button>
      </div>
    </footer>
  </section>

  <section v-else-if="loading" class="panel muted history-loading">正在加载历史记录…</section>
  <section v-else-if="!error && !runs.length" class="panel history-empty">
    <p class="muted">暂无历史记录。</p>
    <RouterLink to="/run">去新建任务</RouterLink>
  </section>
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
const keyword = ref("");
const versionFilter = ref("");
const statusFilter = ref("");
const copyToast = ref("");
let copyToastTimer = null;

function shortId(id) {
  if (!id || id.length <= 14) return id;
  return `${id.slice(0, 8)}…${id.slice(-4)}`;
}

function plainText(s) {
  if (!s) return "";
  return String(s).replace(/\s+/g, " ").trim();
}

function summaryCell(finalOutput) {
  const t = plainText(finalOutput);
  return t || "—";
}

function formatDateTimeCompact(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const d = date.toLocaleDateString();
  const t = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return `${d}\n${t}`;
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

const displayRuns = computed(() => {
  const kw = keyword.value.toLowerCase();
  return runs.value.filter((r) => {
    const versionOk = !versionFilter.value || normalizeVersion(r.agent_version) === versionFilter.value;
    if (!versionOk) return false;
    const s = String(r.status || "").toLowerCase();
    const statusOk =
      !statusFilter.value ||
      (statusFilter.value === "running" ? s !== "completed" && s !== "failed" : s === statusFilter.value);
    if (!statusOk) return false;
    if (!kw) return true;
    const text = `${r.run_id || ""} ${r.user_goal || ""} ${r.task || ""} ${plainText(r.final_output || "")}`.toLowerCase();
    return text.includes(kw);
  });
});

const filterStats = computed(() => {
  let completed = 0;
  let failed = 0;
  let other = 0;
  for (const r of displayRuns.value) {
    const s = String(r.status || "").toLowerCase();
    if (s === "completed" || s === "partial_completed") completed += 1;
    else if (s === "failed") failed += 1;
    else other += 1;
  }
  return { completed, failed, other };
});

function showCopyToast(msg) {
  copyToast.value = msg;
  if (copyToastTimer) clearTimeout(copyToastTimer);
  copyToastTimer = setTimeout(() => {
    copyToast.value = "";
    copyToastTimer = null;
  }, 1600);
}

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
  const ok = window.confirm(`确认删除 run ${shortId(runId)} 吗？关联 replay / trace 将一并删除。`);
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

function clearFilters() {
  keyword.value = "";
  versionFilter.value = "";
  statusFilter.value = "";
}

async function copyRunId(runId) {
  if (!runId) return;
  try {
    await navigator.clipboard.writeText(runId);
    showCopyToast("已复制 run_id");
  } catch {
    error.value = "复制失败，请手动复制。";
  }
}

onMounted(load);
</script>

<style scoped>
.mono {
  font-family: var(--font-mono);
  font-size: 0.8125rem;
}

.history-intro-details {
  margin: 0 0 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: #fafbfc;
  padding: 0 12px;
}

.history-intro-summary {
  cursor: pointer;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text-secondary);
  padding: 10px 0;
  list-style: none;
}

.history-intro-summary::-webkit-details-marker {
  display: none;
}

.history-intro-body {
  margin: 0 0 12px;
  padding-top: 0;
}

.history-toolbar {
  margin-bottom: 12px;
}

.history-table-panel {
  padding: 0;
  overflow: hidden;
}

.history-table-scroll {
  overflow-x: auto;
  max-height: min(70vh, 720px);
  overflow-y: auto;
}

.history-table {
  width: 100%;
  min-width: 1120px;
  table-layout: fixed;
  border-collapse: separate;
  border-spacing: 0;
}

.history-table thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  padding: 10px 12px;
  background: #f0f2f6;
  border-bottom: 1px solid var(--border-subtle);
  box-shadow: 0 1px 0 var(--border-subtle);
}

.th-narrow {
  width: 1%;
  white-space: nowrap;
}

.history-table tbody td {
  height: 76px;
  padding: 12px;
  vertical-align: middle;
  border-bottom: 1px solid var(--border-subtle);
}

.history-row:hover td {
  background: rgba(79, 70, 229, 0.04);
}

.history-cell-text {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-width: 100%;
  line-height: 1.45;
  word-break: break-word;
}

.td-target,
.td-summary {
  vertical-align: middle !important;
}

.history-output {
  color: var(--text-secondary);
}

.history-run-id {
  letter-spacing: 0.01em;
}

.history-run-id--clickable {
  cursor: copy;
  user-select: none;
}

.history-run-id--clickable:hover {
  color: var(--accent-text, #4338ca);
}

.history-time {
  white-space: pre-line;
  line-height: 1.35;
  font-size: 0.8125rem;
  text-align: left;
}

.history-actions {
  text-align: left;
}

.history-action-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.history-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 54px;
  min-height: 32px;
  padding: 6px 10px;
  font-size: 0.8125rem;
  font-weight: 700;
  color: var(--text-primary);
  text-decoration: none;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-strong);
  background: #fff;
  cursor: pointer;
  font-family: inherit;
  line-height: 1;
}

.history-action:hover:not(:disabled) {
  background: rgba(79, 70, 229, 0.08);
  border-color: rgba(79, 70, 229, 0.35);
  color: var(--accent-text);
  text-decoration: none;
}

.history-action--primary {
  color: var(--accent-text);
  border-color: rgba(79, 70, 229, 0.28);
  background: rgba(79, 70, 229, 0.08);
}

.history-action--danger {
  color: var(--danger);
  border-color: rgba(220, 38, 38, 0.18);
  background: rgba(220, 38, 38, 0.06);
}

.history-action--danger:hover:not(:disabled) {
  background: rgba(220, 38, 38, 0.08);
  border-color: rgba(220, 38, 38, 0.3);
  color: var(--danger-hover);
}

.history-stats {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}

.history-stat strong {
  color: var(--text-primary);
}

.history-stat-pill {
  font-size: 0.72rem;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid transparent;
}

.history-stat-pill--ok {
  background: rgba(22, 163, 74, 0.12);
  color: #15803d;
  border-color: rgba(22, 163, 74, 0.2);
}

.history-stat-pill--bad {
  background: rgba(220, 38, 38, 0.12);
  color: #b91c1c;
  border-color: rgba(220, 38, 38, 0.2);
}

.history-stat-pill--muted {
  background: #eef0f4;
  color: var(--text-secondary);
  border-color: var(--border-subtle);
}

.history-pagination {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-top: 1px solid var(--border-subtle);
  background: #fafbfc;
}

.history-page-label {
  margin: 0 6px 0 0;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text-secondary);
}

.history-pagination-right {
  gap: 8px;
}

.history-page-current {
  font-weight: 800;
  color: var(--text-primary);
}

.history-empty-filter,
.history-loading {
  padding: 20px 16px;
  text-align: center;
}

.history-empty {
  text-align: center;
  padding: 28px 20px;
}

.history-empty .muted {
  margin-bottom: 10px;
}

.history-expanded-row td {
  background: #f4f6fb;
  padding: 0;
}

.history-expanded-row pre {
  margin: 0;
  border-radius: 0;
  max-height: 420px;
}

.history-filters {
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(240px, 1fr) 130px 160px auto;
  align-items: center;
}

@media (max-width: 920px) {
  .history-filters {
    grid-template-columns: 1fr;
  }

  .history-task,
  .history-output {
    max-width: none;
  }
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

<style>
/* Teleport 到 body，需非 scoped */
.history-toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  padding: 10px 16px;
  font-size: 0.875rem;
  font-weight: 600;
  color: #fff;
  background: rgba(15, 20, 25, 0.88);
  border-radius: 999px;
  box-shadow: var(--shadow-md, 0 4px 24px rgba(15, 20, 25, 0.15));
  pointer-events: none;
}
</style>
