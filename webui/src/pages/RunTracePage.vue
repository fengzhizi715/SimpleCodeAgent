<template>
  <section class="panel">
    <h2>Run Trace</h2>
    <div class="row">
      <span class="badge">run_id: {{ runId }}</span>
      <span v-if="version" class="badge">{{ formatVersion(version) }}</span>
      <button class="btn-secondary" @click="refresh">刷新</button>
      <RouterLink v-if="normalizeVersion(version) === 'v2'" :to="{ name: 'execution', params: { runId } }">
        返回执行页
      </RouterLink>
      <RouterLink v-else to="/history">返回历史</RouterLink>
    </div>
    <p v-if="error" class="error" style="margin-top: 10px">{{ error }}</p>
  </section>

  <section v-if="trace.length" class="panel">
    <h3>Trace Overview</h3>
    <div class="trace-overview-grid">
      <div class="trace-overview-card">
        <span>事件数</span>
        <strong>{{ timeline.length }}</strong>
      </div>
      <div class="trace-overview-card">
        <span>Session</span>
        <strong>{{ shortId(runMeta.sessionId) }}</strong>
      </div>
      <div class="trace-overview-card">
        <span>Root Run</span>
        <strong>{{ shortId(runMeta.rootRunId) }}</strong>
      </div>
      <div class="trace-overview-card">
        <span>Model</span>
        <strong>{{ runMeta.model || "—" }}</strong>
      </div>
    </div>
    <div class="trace-stat-row">
      <button
        v-for="stat in eventTypeStats"
        :key="stat.type"
        class="trace-stat-chip"
        :class="{ 'is-active': selectedEventType === stat.type }"
        @click="toggleEventTypeFilter(stat.type)"
      >
        {{ stat.type }} · {{ stat.count }}
      </button>
    </div>
  </section>

  <section class="panel">
    <div class="trace-tabs" role="tablist" aria-label="Trace views">
      <button
        class="trace-tab"
        :class="{ 'is-active': activeTab === 'timeline' }"
        type="button"
        role="tab"
        :aria-selected="activeTab === 'timeline'"
        @click="activeTab = 'timeline'"
      >
        Trace Timeline
        <span>{{ filteredTimeline.length }} / {{ trace.length }}</span>
      </button>
      <button
        class="trace-tab"
        :class="{ 'is-active': activeTab === 'raw' }"
        type="button"
        role="tab"
        :aria-selected="activeTab === 'raw'"
        @click="activeTab = 'raw'"
      >
        Raw Trace JSON
        <span>{{ trace.length }}</span>
      </button>
    </div>

    <div v-if="activeTab === 'timeline'" role="tabpanel">
      <div class="trace-section-head">
        <div>
          <h3>Trace Timeline（{{ filteredTimeline.length }} / {{ trace.length }}）</h3>
          <p class="muted">默认展示摘要；用筛选和搜索先定位事件，再展开 payload 详情。</p>
        </div>
        <div class="trace-section-actions">
          <button class="btn-secondary btn-sm" :disabled="!filteredTimeline.length" @click="expandFilteredEvents">
            展开当前结果
          </button>
          <button class="btn-secondary btn-sm" :disabled="!expandedEventIds.size" @click="collapseAllEvents">
            全部收起
          </button>
        </div>
      </div>

      <div v-if="trace.length" class="trace-filter-bar">
        <label>
          <span>事件类型</span>
          <select v-model="selectedEventType">
            <option value="">全部事件</option>
            <option v-for="stat in eventTypeStats" :key="stat.type" :value="stat.type">
              {{ stat.type }}（{{ stat.count }}）
            </option>
          </select>
        </label>
        <label class="trace-filter-search">
          <span>关键词</span>
          <input v-model.trim="searchKeyword" type="search" placeholder="搜索 actor / action / message / summary / payload" />
        </label>
        <button class="btn-secondary btn-sm" :disabled="!hasActiveFilters" @click="clearFilters">清空筛选</button>
      </div>

      <ol v-if="filteredTimeline.length" class="trace-timeline">
        <li v-for="item in filteredTimeline" :key="item.id" class="trace-event" :class="eventClass(item.event_type)">
          <div class="trace-event-marker">{{ item.index + 1 }}</div>
          <article class="trace-event-card">
            <header class="trace-event-head">
              <div class="trace-event-title">
                <span class="trace-type">{{ item.event_type || "event" }}</span>
                <strong>{{ item.message || humanizeEventType(item.event_type) }}</strong>
              </div>
              <time>{{ formatTime(item.created_at) }}</time>
            </header>

            <div class="trace-chip-row">
              <span>actor: {{ inferActor(item) }}</span>
              <span>action: {{ item.action || humanizeEventType(item.event_type) }}</span>
              <span>status: {{ inferStatus(item) }}</span>
              <span v-if="durationText(item)">duration: {{ durationText(item) }}</span>
            </div>

            <p class="trace-summary">{{ summaryFor(item) }}</p>

            <div v-if="payloadHighlights(item).length" class="trace-highlight-list">
              <span v-for="highlight in payloadHighlights(item)" :key="highlight">{{ highlight }}</span>
            </div>

            <div class="trace-event-actions">
              <button class="btn-secondary btn-sm" @click="toggleEvent(item.id)">
                {{ isExpanded(item.id) ? "收起详情" : "展开详情" }}
              </button>
            </div>

            <div v-if="isExpanded(item.id)" class="trace-event-detail">
              <dl>
                <div>
                  <dt>event_id</dt>
                  <dd>{{ item.id }}</dd>
                </div>
                <div>
                  <dt>run_id</dt>
                  <dd>{{ item.run_id || "—" }}</dd>
                </div>
                <div>
                  <dt>root_run_id</dt>
                  <dd>{{ item.root_run_id || "—" }}</dd>
                </div>
                <div>
                  <dt>parent_run_id</dt>
                  <dd>{{ item.parent_run_id || "—" }}</dd>
                </div>
                <div>
                  <dt>parent_event_id</dt>
                  <dd>{{ item.parent_event_id || "—" }}</dd>
                </div>
                <div>
                  <dt>started_at</dt>
                  <dd>{{ item.started_at || "—" }}</dd>
                </div>
                <div>
                  <dt>ended_at</dt>
                  <dd>{{ item.ended_at || "—" }}</dd>
                </div>
              </dl>
              <h4>Payload</h4>
              <JsonBlock :data="item.payload || {}" />
            </div>
          </article>
        </li>
      </ol>
      <p v-else-if="trace.length" class="muted">没有匹配当前筛选条件的 Trace 事件。</p>
      <p v-else class="muted">暂无 Trace 数据。</p>
    </div>

    <div v-else role="tabpanel">
      <div class="trace-section-head">
        <div>
          <h3>Raw Trace JSON</h3>
          <p class="muted">完整原始数据只在本 Tab 展示，用于排查字段级问题。</p>
        </div>
      </div>
      <JsonBlock :data="trace" />
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import JsonBlock from "../components/JsonBlock.vue";
import { getRunReplay, getRunTrace } from "../api";

const props = defineProps({
  runId: { type: String, required: true },
});

const trace = ref([]);
const runMetadata = ref(null);
const error = ref("");
const expandedEventIds = ref(new Set());
const searchKeyword = ref("");
const selectedEventType = ref("");
const activeTab = ref("timeline");
const route = useRoute();
const version = ref(String(route.query.version || ""));

const timeline = computed(() =>
  trace.value.map((item, index) => ({
    ...item,
    index,
  })),
);

const eventTypeStats = computed(() => {
  const counts = new Map();
  for (const item of trace.value) {
    const type = item.event_type || "unknown";
    counts.set(type, (counts.get(type) || 0) + 1);
  }
  return [...counts.entries()]
    .map(([type, count]) => ({ type, count }))
    .sort((a, b) => b.count - a.count || a.type.localeCompare(b.type));
});

const filteredTimeline = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase();
  return timeline.value.filter((item) => {
    if (selectedEventType.value && item.event_type !== selectedEventType.value) {
      return false;
    }
    if (!keyword) return true;
    return searchableText(item).includes(keyword);
  });
});

const hasActiveFilters = computed(() => Boolean(selectedEventType.value || searchKeyword.value.trim()));

const runMeta = computed(() => {
  const first = trace.value[0] || {};
  const llmEvent = trace.value.find((item) => item?.payload?.model);
  const replayRun = runMetadata.value || {};
  return {
    sessionId: replayRun.session_id || first.session_id || "",
    rootRunId: first.root_run_id || replayRun.run_id || first.run_id || "",
    model: llmEvent?.payload?.model || replayRun.model || "",
  };
});

function normalizeVersion(v) {
  if (!v || typeof v !== "string") return "";
  const s = v.trim().toLowerCase();
  if (s === "v1" || s === "v2" || s === "v3") return s;
  if (s.startsWith("v")) return s;
  return `v${s}`;
}

function formatVersion(v) {
  const normalized = normalizeVersion(v);
  return normalized ? normalized.toUpperCase() : "";
}

function shortId(value) {
  if (!value || typeof value !== "string") return "—";
  if (value.length <= 13) return value;
  return `${value.slice(0, 8)}...${value.slice(-4)}`;
}

function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function humanizeEventType(type) {
  if (!type || typeof type !== "string") return "未命名事件";
  return type.replaceAll("_", " ");
}

function inferActor(item) {
  if (item.actor) return item.actor;
  const type = item.event_type || "";
  if (type.startsWith("llm_")) return "llm";
  if (type.startsWith("tool_")) return "tool";
  if (type.startsWith("memory_")) return "memory";
  if (type.startsWith("run_")) return "runtime";
  if (type.startsWith("step_")) return "agent_loop";
  return "system";
}

function inferStatus(item) {
  if (item.status) return item.status;
  const type = item.event_type || "";
  if (type.endsWith("_failed")) return "failed";
  if (type.endsWith("_started") || type.endsWith("_called")) return "started";
  if (type.endsWith("_finished") || type.endsWith("_responded") || type.endsWith("_result")) return "completed";
  return "recorded";
}

function eventClass(type) {
  if (!type) return "";
  if (type.includes("failed") || type.includes("error")) return "is-danger";
  if (type.startsWith("llm_")) return "is-llm";
  if (type.startsWith("tool_")) return "is-tool";
  if (type.startsWith("memory_")) return "is-memory";
  return "is-runtime";
}

function durationText(item) {
  if (!item.started_at || !item.ended_at) return "";
  const started = new Date(item.started_at).getTime();
  const ended = new Date(item.ended_at).getTime();
  if (Number.isNaN(started) || Number.isNaN(ended) || ended < started) return "";
  const ms = ended - started;
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function clipText(value, maxLength = 220) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
}

function payloadHighlights(item) {
  const payload = item.payload;
  if (!payload || typeof payload !== "object") return [];
  const highlights = [];
  if (payload.model) highlights.push(`model: ${payload.model}`);
  if (payload.step_count !== undefined) highlights.push(`step_count: ${payload.step_count}`);
  if (payload.finish_reason) highlights.push(`finish_reason: ${payload.finish_reason}`);
  if (payload.tool_name) highlights.push(`tool: ${payload.tool_name}`);
  if (payload.file_path) highlights.push(`file: ${payload.file_path}`);
  if (payload.error_type) highlights.push(`error_type: ${payload.error_type}`);
  return highlights;
}

function payloadSummary(payload) {
  if (!payload || typeof payload !== "object") return "";
  if (payload.summary) return clipText(payload.summary);
  if (payload.result) return clipText(payload.result);
  if (payload.error) return clipText(payload.error);
  if (payload.task) return `task: ${clipText(payload.task)}`;
  const keys = Object.keys(payload);
  if (!keys.length) return "";
  return `payload keys: ${keys.slice(0, 8).join(", ")}`;
}

function summaryFor(item) {
  return (
    clipText(item.output_summary) ||
    clipText(item.input_summary) ||
    payloadSummary(item.payload) ||
    "—"
  );
}

function searchableText(item) {
  const parts = [
    item.event_type,
    item.actor,
    item.action,
    item.status,
    item.message,
    item.input_summary,
    item.output_summary,
    payloadSummary(item.payload),
  ];
  if (item.payload && typeof item.payload === "object") {
    parts.push(JSON.stringify(item.payload));
  }
  return parts.filter(Boolean).join(" ").toLowerCase();
}

function isExpanded(id) {
  return expandedEventIds.value.has(id);
}

function toggleEvent(id) {
  const next = new Set(expandedEventIds.value);
  if (next.has(id)) {
    next.delete(id);
  } else {
    next.add(id);
  }
  expandedEventIds.value = next;
}

function expandFilteredEvents() {
  expandedEventIds.value = new Set(filteredTimeline.value.map((item) => item.id));
}

function collapseAllEvents() {
  expandedEventIds.value = new Set();
}

function clearFilters() {
  selectedEventType.value = "";
  searchKeyword.value = "";
}

function toggleEventTypeFilter(type) {
  selectedEventType.value = selectedEventType.value === type ? "" : type;
}

async function refresh() {
  error.value = "";
  try {
    const data = await getRunTrace(props.runId);
    trace.value = Array.isArray(data.events) ? data.events : [];
    await refreshRunMetadata();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载 Trace 失败";
  }
}

async function refreshRunMetadata() {
  runMetadata.value = null;
  if (normalizeVersion(version.value) !== "v2") return;

  try {
    const replay = await getRunReplay(props.runId);
    runMetadata.value = replay?.run || null;
  } catch (_err) {
    // Trace 数据本身仍然可用时，不因为补充 metadata 失败而阻塞页面。
    runMetadata.value = null;
  }
}

onMounted(refresh);
</script>

<style scoped>
.trace-overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.trace-overview-card {
  padding: 14px 16px;
  border: 1px solid var(--border-subtle);
  border-radius: 16px;
  background:
    linear-gradient(135deg, rgba(79, 70, 229, 0.08), transparent 52%),
    #fff;
  min-width: 0;
}

.trace-overview-card span {
  display: block;
  color: var(--text-muted);
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.trace-overview-card strong {
  display: block;
  margin-top: 5px;
  overflow: hidden;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 0.95rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-stat-row,
.trace-chip-row,
.trace-highlight-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.trace-stat-row {
  margin-top: 14px;
}

.trace-tabs {
  display: flex;
  gap: 8px;
  margin: -4px 0 18px;
  padding: 6px;
  overflow-x: auto;
  border: 1px solid rgba(37, 99, 235, 0.14);
  border-radius: 18px;
  background:
    linear-gradient(135deg, rgba(37, 99, 235, 0.08), rgba(14, 116, 144, 0.04)),
    #f8fafc;
}

.trace-tab {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 40px;
  padding: 9px 14px;
  border: 1px solid rgba(100, 116, 139, 0.12);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.66);
  color: #475569;
  white-space: nowrap;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.trace-tab:hover {
  border-color: rgba(37, 99, 235, 0.22);
  background: #fff;
  color: #1d4ed8;
}

.trace-tab span {
  border-radius: 999px;
  padding: 2px 7px;
  background: rgba(71, 85, 105, 0.1);
  color: #64748b;
  font-family: var(--font-mono);
  font-size: 0.72rem;
}

.trace-tab.is-active {
  border-color: rgba(29, 78, 216, 0.35);
  background: linear-gradient(135deg, #1d4ed8 0%, #0f766e 100%);
  color: #fff;
  box-shadow: 0 8px 22px rgba(37, 99, 235, 0.22);
}

.trace-tab.is-active span {
  background: rgba(255, 255, 255, 0.18);
  color: #fff;
}

.trace-section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.trace-section-head h3 {
  margin-bottom: 4px;
}

.trace-section-head p {
  margin: 0;
}

.trace-section-actions {
  display: flex;
  flex-shrink: 0;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.trace-filter-bar {
  display: grid;
  grid-template-columns: minmax(160px, 220px) minmax(240px, 1fr) auto;
  gap: 12px;
  align-items: end;
  margin-bottom: 18px;
  padding: 14px;
  border: 1px solid var(--border-subtle);
  border-radius: 16px;
  background: #f8fafc;
}

.trace-filter-bar label {
  margin-bottom: 0;
}

.trace-filter-bar label span {
  display: block;
  margin-bottom: 6px;
}

.trace-stat-chip,
.trace-chip-row span,
.trace-highlight-list span {
  border-radius: 999px;
  padding: 4px 9px;
  font-size: 0.75rem;
  font-weight: 650;
}

.trace-stat-chip {
  border: 1px solid rgba(79, 70, 229, 0.18);
  background: var(--accent-soft);
  color: var(--accent-text);
  cursor: pointer;
}

button.trace-stat-chip {
  font-family: inherit;
  line-height: 1.2;
}

.trace-stat-chip:hover,
.trace-stat-chip.is-active {
  border-color: rgba(79, 70, 229, 0.45);
  background: #4f46e5;
  color: #fff;
}

.trace-timeline {
  position: relative;
  display: grid;
  gap: 14px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.trace-timeline::before {
  position: absolute;
  top: 18px;
  bottom: 18px;
  left: 15px;
  width: 2px;
  background: linear-gradient(180deg, rgba(79, 70, 229, 0.3), rgba(15, 23, 42, 0.08));
  content: "";
}

.trace-event {
  position: relative;
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  gap: 13px;
}

.trace-event-marker {
  z-index: 1;
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border: 2px solid #fff;
  border-radius: 999px;
  background: #64748b;
  color: #fff;
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.16);
  font-size: 0.75rem;
  font-weight: 800;
}

.trace-event.is-llm .trace-event-marker {
  background: #4f46e5;
}

.trace-event.is-tool .trace-event-marker {
  background: #0f766e;
}

.trace-event.is-memory .trace-event-marker {
  background: #b45309;
}

.trace-event.is-danger .trace-event-marker {
  background: var(--danger);
}

.trace-event-card {
  padding: 15px 16px;
  border: 1px solid var(--border-subtle);
  border-radius: 18px;
  background: #fff;
  box-shadow: var(--shadow-sm);
}

.trace-event-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.trace-event-title {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.trace-event-title strong {
  font-size: 0.98rem;
}

.trace-event-head time {
  flex-shrink: 0;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 0.75rem;
}

.trace-type {
  border-radius: 999px;
  padding: 4px 9px;
  background: #eef2ff;
  color: #3730a3;
  font-family: var(--font-mono);
  font-size: 0.72rem;
  font-weight: 800;
}

.trace-chip-row {
  margin-top: 10px;
}

.trace-chip-row span {
  background: #f1f5f9;
  color: #475569;
}

.trace-summary {
  margin: 12px 0 0;
  color: var(--text-secondary);
  line-height: 1.65;
}

.trace-highlight-list {
  margin-top: 10px;
}

.trace-highlight-list span {
  border: 1px solid rgba(13, 148, 136, 0.18);
  background: rgba(13, 148, 136, 0.08);
  color: #0f766e;
  font-family: var(--font-mono);
}

.trace-event-actions {
  margin-top: 12px;
}

.trace-event-detail {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--border-subtle);
}

.trace-event-detail dl {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 9px 14px;
  margin: 0 0 14px;
}

.trace-event-detail dl > div {
  min-width: 0;
}

.trace-event-detail dt {
  color: var(--text-muted);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.trace-event-detail dd {
  margin: 3px 0 0;
  overflow-wrap: anywhere;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 0.78rem;
}

.trace-event-detail h4 {
  margin: 0 0 8px;
  color: var(--text-secondary);
  font-size: 0.82rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

@media (max-width: 820px) {
  .trace-overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .trace-section-head {
    flex-direction: column;
  }

  .trace-section-actions {
    justify-content: flex-start;
  }

  .trace-filter-bar {
    grid-template-columns: 1fr;
  }

  .trace-event-head {
    flex-direction: column;
  }

  .trace-event-detail dl {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 560px) {
  .trace-overview-grid {
    grid-template-columns: 1fr;
  }
}
</style>
