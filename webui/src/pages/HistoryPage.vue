<template>
  <section class="panel history-page">
    <div class="history-header">
      <h2 class="history-title">运行历史</h2>
      <div class="history-header-actions">
        <button class="btn-secondary btn-sm" :disabled="loading" @click="load">
          {{ loading ? "加载中…" : "刷新" }}
        </button>
        <RouterLink class="btn-primary btn-sm" to="/run">新建任务</RouterLink>
      </div>
    </div>

    <div class="history-toolbar">
      <div class="history-search-wrap">
        <svg class="search-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input v-model.trim="keyword" placeholder="搜索任务、摘要或 run_id" />
      </div>
      <select v-model="versionFilter" class="filter-select">
        <option value="">全部版本</option>
        <option value="v1">V1</option>
        <option value="v2">V2</option>
        <option value="v3">V3</option>
      </select>
      <select v-model="statusFilter" class="filter-select">
        <option value="">全部状态</option>
        <option value="completed">完成</option>
        <option value="failed">失败</option>
        <option value="running">进行中</option>
      </select>
      <button v-if="hasActiveFilters" class="btn-text btn-sm" type="button" @click="clearFilters">清空</button>
    </div>

    <div v-if="runs.length" class="history-stats-bar">
      <span class="history-stat-text">共 <strong>{{ total }}</strong> 条</span>
      <span v-if="filterStats.completed" class="history-stat-pill history-stat-pill--ok">完成 {{ filterStats.completed }}</span>
      <span v-if="filterStats.failed" class="history-stat-pill history-stat-pill--bad">失败 {{ filterStats.failed }}</span>
      <span v-if="filterStats.other" class="history-stat-pill history-stat-pill--muted">其它 {{ filterStats.other }}</span>
      <div class="history-stats-spacer"></div>
      <label v-if="displayRuns.length" class="history-bulk-toggle">
        <input type="checkbox" :checked="allVisibleSelected" :disabled="bulkDeleting" @change="toggleSelectAllVisible" />
        全选
      </label>
      <span v-if="selectedCount" class="history-selection-count">已选 {{ selectedCount }}</span>
      <button
        v-if="selectedCount"
        class="btn-text btn-sm history-bulk-delete-btn"
        type="button"
        :disabled="bulkDeleting"
        @click="removeSelectedRuns"
      >
        {{ bulkDeleting ? `删除中 (${bulkDeleteProgressText})` : "批量删除" }}
      </button>
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
          <col style="width: 36px" />
          <col style="width: 56px" />
          <col style="width: 72px" />
          <col style="width: 100px" />
          <col style="width: 20%" />
          <col style="width: 28%" />
          <col style="width: 80px" />
          <col style="width: 160px" />
        </colgroup>
        <thead>
          <tr>
            <th class="th-checkbox">
              <input type="checkbox" :checked="allVisibleSelected" :disabled="bulkDeleting || !displayRuns.length" @change="toggleSelectAllVisible" />
            </th>
            <th class="th-narrow">版本</th>
            <th class="th-narrow">状态</th>
            <th class="th-run-id">Run ID</th>
            <th>目标</th>
            <th>结果摘要</th>
            <th class="th-time">时间</th>
            <th class="th-actions history-actions-sticky">操作</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="r in displayRuns" :key="r.run_id">
            <tr class="history-row">
              <td class="history-checkbox-cell">
                <input type="checkbox" :checked="isSelected(r.run_id)" :disabled="bulkDeleting" @change="toggleSelectedRun(r.run_id)" />
              </td>
              <td>
                <span class="agent-version" :class="versionClass(r.agent_version)">{{ formatVersion(r.agent_version) }}</span>
              </td>
              <td>
                <span class="status-pill" :class="statusClass(r.status)">{{ formatStatus(r.status) }}</span>
              </td>
              <td class="mono history-run-id-cell">
                <button class="history-run-id-btn" :title="`点击复制：${r.run_id}`" @click="copyRunId(r.run_id)">
                  <svg class="copy-icon" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                  <span class="history-run-id">{{ shortId(r.run_id) }}</span>
                </button>
              </td>
              <td class="td-target" :title="r.user_goal || r.task">
                <div class="history-cell-text history-task">{{ r.user_goal || r.task || "—" }}</div>
              </td>
              <td class="td-summary" :title="extractSummary(r)">
                <div class="history-cell-text history-output">{{ extractSummary(r) }}</div>
              </td>
              <td class="muted history-time td-time">{{ formatTimeAgo(r.updated_at) }}</td>
              <td class="history-actions td-actions history-actions-sticky">
                <div class="history-action-group">
                  <template v-if="normalizeVersion(r.agent_version) === 'v2' || normalizeVersion(r.agent_version) === 'v3'">
                    <RouterLink class="history-action history-action--primary" :to="{ name: 'execution', params: { runId: r.run_id } }">详情</RouterLink>
                    <RouterLink class="history-action history-action--secondary" :to="{ name: 'trace', params: { runId: r.run_id }, query: { version: normalizeVersion(r.agent_version) } }">Trace</RouterLink>
                  </template>
                  <template v-else>
                    <button type="button" class="history-action history-action--primary" @click="toggleExpanded(r.run_id)">
                      {{ expandedRunId === r.run_id ? "收起" : "结果" }}
                    </button>
                    <RouterLink class="history-action history-action--secondary" :to="{ name: 'trace', params: { runId: r.run_id }, query: { version: normalizeVersion(r.agent_version) } }">Trace</RouterLink>
                  </template>
                  <button
                    type="button"
                    class="history-action history-action--danger"
                    :disabled="deletingRunId === r.run_id || bulkDeleting"
                    :title="deletingRunId === r.run_id ? '删除中' : '删除'"
                    @click="removeRun(r.run_id)"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                    <span>删除</span>
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="expandedRunId === r.run_id" class="history-expanded-row">
              <td colspan="8">
                <pre>{{ r.final_output || "暂无结果内容。" }}</pre>
              </td>
            </tr>
          </template>
          <tr v-if="!displayRuns.length">
            <td colspan="8" class="muted history-empty-filter">当前筛选条件下无结果，可尝试清空筛选。</td>
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
          第 <span class="history-page-current">{{ currentPage }}</span> / {{ totalPages }} 页
        </span>
        <button class="btn-secondary btn-sm" type="button" :disabled="currentPage <= 1 || loading" @click="goPrevPage">上一页</button>
        <button class="btn-secondary btn-sm" type="button" :disabled="currentPage >= totalPages || loading" @click="goNextPage">下一页</button>
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
const bulkDeleting = ref(false);
const bulkDeleteCompleted = ref(0);
const bulkDeleteTotal = ref(0);
const total = ref(0);
const pageSize = ref(20);
const page = ref(1);
const expandedRunId = ref("");
const keyword = ref("");
const versionFilter = ref("");
const statusFilter = ref("");
const copyToast = ref("");
const selectedRunIds = ref(new Set());
let copyToastTimer = null;

function shortId(id) {
  if (!id || id.length <= 14) return id;
  return `${id.slice(0, 8)}…${id.slice(-4)}`;
}

function plainText(s) {
  if (!s) return "";
  return String(s).replace(/\s+/g, " ").trim();
}

function extractSummary(r) {
  if (!r.final_output) return "—";
  try {
    const parsed = typeof r.final_output === "string" ? JSON.parse(r.final_output) : r.final_output;
    if (parsed && typeof parsed === "object") {
      if (parsed.summary) return String(parsed.summary);
      if (parsed.status) return `状态: ${parsed.status}`;
      if (parsed.run_id) return `Run ${shortId(parsed.run_id)}`;
      const keys = Object.keys(parsed).filter((k) => typeof parsed[k] === "string" && parsed[k].length < 200);
      if (keys.length) return String(parsed[keys[0]]);
    }
    return plainText(r.final_output).slice(0, 120);
  } catch {
    return plainText(r.final_output).slice(0, 120);
  }
}

function formatStatus(status) {
  const s = String(status || "").toLowerCase();
  if (s === "completed") return "完成";
  if (s === "partial_completed") return "部分完成";
  if (s === "failed") return "失败";
  if (s === "running") return "进行中";
  return status || "未知";
}

function formatTimeAgo(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "刚刚";
  if (diffMins < 60) return `${diffMins} 分钟前`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours} 小时前`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays} 天前`;
  return date.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
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

const hasActiveFilters = computed(() => keyword.value || versionFilter.value || statusFilter.value);

async function load() {
  error.value = "";
  loading.value = true;
  try {
    const data = await listRuns({ limit: pageSize.value, offset: (page.value - 1) * pageSize.value });
    runs.value = Array.isArray(data.runs) ? data.runs : [];
    total.value = Number(data.total || 0);
    const visibleRunIds = new Set(runs.value.map((item) => item.run_id).filter(Boolean));
    selectedRunIds.value = new Set(
      [...selectedRunIds.value].filter((runId) => visibleRunIds.has(runId))
    );
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

const selectedCount = computed(() => selectedRunIds.value.size);

const allVisibleSelected = computed(() => {
  if (!displayRuns.value.length) return false;
  return displayRuns.value.every((item) => item.run_id && selectedRunIds.value.has(item.run_id));
});

const bulkDeleteProgressText = computed(() => {
  if (!bulkDeleteTotal.value) return "0/0";
  return `${bulkDeleteCompleted.value}/${bulkDeleteTotal.value}`;
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
    const next = new Set(selectedRunIds.value);
    next.delete(runId);
    selectedRunIds.value = next;
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

async function removeSelectedRuns() {
  const runIds = displayRuns.value
    .map((item) => item.run_id)
    .filter((runId) => runId && selectedRunIds.value.has(runId));
  if (!runIds.length) return;

  const ok = window.confirm(
    `确认批量删除 ${runIds.length} 条运行记录吗？关联 replay / trace 将一并删除。`
  );
  if (!ok) return;

  bulkDeleting.value = true;
  bulkDeleteCompleted.value = 0;
  bulkDeleteTotal.value = runIds.length;
  error.value = "";

  const failedRunIds = [];
  for (const runId of runIds) {
    try {
      await deleteRun(runId);
      bulkDeleteCompleted.value += 1;
      if (expandedRunId.value === runId) {
        expandedRunId.value = "";
      }
    } catch (_err) {
      failedRunIds.push(runId);
    }
  }

  if (failedRunIds.length) {
    error.value = `批量删除完成，但有 ${failedRunIds.length} 条删除失败。`;
    selectedRunIds.value = new Set(failedRunIds);
  } else {
    selectedRunIds.value = new Set();
  }

  await load();
  bulkDeleting.value = false;
  bulkDeleteCompleted.value = 0;
  bulkDeleteTotal.value = 0;
}

function toggleExpanded(runId) {
  expandedRunId.value = expandedRunId.value === runId ? "" : runId;
}

function isSelected(runId) {
  return selectedRunIds.value.has(runId);
}

function toggleSelectedRun(runId) {
  const next = new Set(selectedRunIds.value);
  if (next.has(runId)) {
    next.delete(runId);
  } else {
    next.add(runId);
  }
  selectedRunIds.value = next;
}

function toggleSelectAllVisible() {
  const next = new Set(selectedRunIds.value);
  if (allVisibleSelected.value) {
    for (const item of displayRuns.value) {
      if (item.run_id) {
        next.delete(item.run_id);
      }
    }
  } else {
    for (const item of displayRuns.value) {
      if (item.run_id) {
        next.add(item.run_id);
      }
    }
  }
  selectedRunIds.value = next;
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

/* ---- Page Header ---- */
.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.history-title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--text-primary);
}

.history-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ---- Toolbar ---- */
.history-toolbar {
  display: grid;
  grid-template-columns: 1fr auto auto auto;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}

.history-search-wrap {
  position: relative;
  min-width: 0;
}

.search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
  pointer-events: none;
  width: 15px;
  height: 15px;
}

.history-search-wrap input {
  width: 100%;
  padding-left: 34px;
  height: 34px;
  font-size: 0.8125rem;
}

.filter-select {
  height: 34px;
  padding: 0 26px 0 10px;
  font-size: 0.8125rem;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: #fff;
  color: var(--text-primary);
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 7px center;
  background-size: 12px;
  width: 100px;
  flex-shrink: 0;
}

.filter-select:hover {
  border-color: var(--border-strong);
}

.filter-select:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.1);
}

@media (max-width: 768px) {
  .history-toolbar {
    grid-template-columns: 1fr;
  }
  .filter-select {
    width: 100%;
  }
}

/* ---- Stats Bar ---- */
.history-stats-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 6px 0;
  border-top: 1px solid var(--border-subtle);
  margin-bottom: 4px;
  min-height: 32px;
}

.history-stat-text {
  font-size: 0.8125rem;
  color: var(--text-secondary);
}

.history-stat-text strong {
  color: var(--text-primary);
}

.history-stats-spacer {
  flex: 1;
}

.history-bulk-toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 0.8125rem;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 4px;
  white-space: nowrap;
  user-select: none;
}

.history-bulk-toggle:hover {
  background: rgba(0, 0, 0, 0.04);
  color: var(--text-primary);
}

.history-bulk-toggle input[type="checkbox"] {
  cursor: pointer;
  margin: 0;
}

.history-selection-count {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--accent-text, #4338ca);
  padding: 2px 8px;
  background: rgba(79, 70, 229, 0.08);
  border-radius: 4px;
  white-space: nowrap;
}

.history-bulk-delete-btn:not(:disabled) {
  color: var(--danger);
}

.history-bulk-delete-btn:not(:disabled):hover {
  background: rgba(220, 38, 38, 0.06);
}

/* ---- Stat Pills ---- */
.history-stat-pill {
  font-size: 0.72rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid transparent;
}

.history-stat-pill--ok {
  background: rgba(22, 163, 74, 0.10);
  color: #15803d;
  border-color: rgba(22, 163, 74, 0.18);
}

.history-stat-pill--bad {
  background: rgba(220, 38, 38, 0.10);
  color: #b91c1c;
  border-color: rgba(220, 38, 38, 0.18);
}

.history-stat-pill--muted {
  background: #eef0f4;
  color: var(--text-secondary);
  border-color: var(--border-subtle);
}

/* ---- Table ---- */
.history-table-panel {
  padding: 0;
  overflow: hidden;
}

.history-table-scroll {
  overflow-x: auto;
  max-height: min(65vh, 640px);
  overflow-y: auto;
}

.history-table {
  width: 100%;
  min-width: 820px;
  table-layout: fixed;
  border-collapse: separate;
  border-spacing: 0;
}

.history-table thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  padding: 8px 10px;
  background: #f8f9fb;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.th-narrow {
  width: 1%;
  white-space: nowrap;
}

.th-checkbox,
.history-checkbox-cell {
  width: 36px;
  text-align: center;
}

.th-run-id {
  white-space: nowrap;
  text-align: center;
}

.history-table tbody td {
  height: 48px;
  padding: 6px 10px;
  vertical-align: middle;
  border-bottom: 1px solid var(--border-subtle);
}

.history-row:hover td {
  background: rgba(79, 70, 229, 0.02);
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
  font-size: 0.8125rem;
}

.history-run-id-cell {
  padding: 0;
  text-align: center;
}

.history-run-id-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 6px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--text-primary);
  border-radius: 4px;
  transition: all 0.15s;
  line-height: 1.3;
  justify-content: center;
  width: 100%;
}

.history-run-id-btn:hover {
  background: rgba(79, 70, 229, 0.08);
  color: var(--accent-text, #4338ca);
}

.copy-icon {
  opacity: 0;
  transition: opacity 0.15s;
  flex-shrink: 0;
}

.history-run-id-btn:hover .copy-icon {
  opacity: 0.5;
}

.history-run-id {
  letter-spacing: 0.01em;
  font-weight: 500;
}

.history-task {
  font-weight: 500;
  color: var(--text-primary);
  font-size: 0.85rem;
}

.history-time {
  white-space: nowrap;
  font-size: 0.8125rem;
  text-align: left;
}

/* ---- Actions ---- */
.history-actions {
  text-align: left;
}

.history-actions-sticky {
  position: sticky;
  right: 0;
  z-index: 3;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0), rgba(255, 255, 255, 0.9) 20%, #fff 40%);
}

tbody .history-actions-sticky {
  z-index: 1;
}

.history-action-group {
  display: flex;
  align-items: center;
  gap: 4px;
}

.history-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 26px;
  padding: 3px 8px;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-primary);
  text-decoration: none;
  border-radius: 4px;
  border: 1px solid var(--border-subtle);
  background: transparent;
  cursor: pointer;
  font-family: inherit;
  line-height: 1;
  white-space: nowrap;
  gap: 3px;
}

.history-action:hover:not(:disabled) {
  background: rgba(79, 70, 229, 0.06);
  border-color: rgba(79, 70, 229, 0.2);
  color: var(--accent-text);
  text-decoration: none;
}

.history-action--primary {
  color: #fff;
  border-color: var(--accent);
  background: var(--accent);
}

.history-action--primary:hover:not(:disabled) {
  background: var(--accent-hover, #3730a3);
  border-color: var(--accent-hover, #3730a3);
  color: #fff;
}

.history-action--secondary {
  color: var(--text-secondary);
  border-color: var(--border-subtle);
}

.history-action--secondary:hover:not(:disabled) {
  color: var(--text-primary);
  border-color: var(--border-strong);
  background: rgba(0, 0, 0, 0.03);
}

.history-action--danger {
  color: var(--danger);
  border-color: rgba(220, 38, 38, 0.15);
  background: rgba(220, 38, 38, 0.04);
  gap: 3px;
  padding: 3px 10px;
}

.history-action--danger:hover:not(:disabled) {
  color: #fff;
  background: var(--danger);
  border-color: var(--danger);
}

.history-action--danger svg {
  flex-shrink: 0;
}

/* ---- Pagination ---- */
.history-pagination {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
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
  font-weight: 700;
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

/* ---- Status Pills ---- */
.status-pill {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 0.72rem;
  font-weight: 600;
  border: 1px solid transparent;
}

.status-pill--ok {
  background: rgba(22, 163, 74, 0.10);
  color: #15803d;
  border-color: rgba(22, 163, 74, 0.18);
}

.status-pill--failed {
  background: rgba(220, 38, 38, 0.10);
  color: #b91c1c;
  border-color: rgba(220, 38, 38, 0.18);
}

.status-pill--running {
  background: #eef0f4;
  color: var(--text-secondary);
  border-color: var(--border-subtle);
}

@media (max-width: 920px) {
  .history-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .history-filters {
    width: 100%;
  }

  .history-task,
  .history-output {
    max-width: none;
  }
}
</style>

<style>
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
