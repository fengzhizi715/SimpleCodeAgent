<template>
  <section class="panel">
    <h2>Run Execution</h2>
    <div class="row">
      <span class="badge">run_id: {{ runId }}</span>
      <button class="btn-secondary" @click="fetchReplay">手动刷新</button>
      <button class="btn-secondary" @click="goTrace">查看 Trace</button>
    </div>
    <p class="muted" style="margin-top: 8px">轮询状态：{{ polling ? "开启" : "关闭" }}</p>
    <p v-if="error" class="error">{{ error }}</p>
  </section>

  <section class="panel" v-if="replay.run">
    <h3>运行摘要</h3>
    <table>
      <tbody>
        <tr><th>status</th><td>{{ replay.run.status }}</td></tr>
        <tr><th>session_id</th><td>{{ replay.run.session_id }}</td></tr>
        <tr><th>task</th><td>{{ replay.run.task }}</td></tr>
        <tr><th>model</th><td>{{ replay.run.model }}</td></tr>
        <tr><th>step_count</th><td>{{ replay.run.step_count }}</td></tr>
      </tbody>
    </table>
  </section>

  <section class="panel" v-if="flowNodes.length">
    <h3>执行流程（可视化）</h3>
    <div class="flow-legend">
      <span class="flow-legend-item"><i class="dot dot-completed" /> completed</span>
      <span class="flow-legend-item"><i class="dot dot-running" /> running</span>
      <span class="flow-legend-item"><i class="dot dot-failed" /> failed</span>
      <span class="flow-legend-item"><i class="dot dot-unknown" /> unknown</span>
    </div>
    <div class="flow-layout">
      <div class="flow-lane">
        <div class="flow-chain">
          <template v-for="(node, index) in flowNodes" :key="node.id">
            <button
              type="button"
              class="flow-node-btn"
              :class="[
                `is-${normalizeStatus(node.status)}`,
                selectedDelegationId === node.id ? 'is-selected' : '',
              ]"
              @click="selectDelegation(node.id)"
            >
              <span class="flow-node-index">#{{ index + 1 }}</span>
              <span class="flow-node-agent">{{ node.agent }}</span>
              <span class="flow-node-status">{{ node.status || "unknown" }}</span>
              <span class="flow-node-time">{{ node.startedAtLabel }}</span>
            </button>
            <span v-if="index < flowNodes.length - 1" class="flow-arrow">→</span>
          </template>
        </div>
      </div>
      <aside class="flow-detail">
        <h4>节点摘要（只读）</h4>
        <template v-if="selectedDelegation">
          <div class="flow-detail-meta">
            <p class="muted"><strong>Agent：</strong>{{ selectedDelegation.target_agent || "—" }}</p>
            <p class="muted"><strong>状态：</strong>{{ selectedDelegation.status || "—" }}</p>
            <p class="muted"><strong>Step ID：</strong>{{ selectedDelegation.step_id || "—" }}</p>
            <p class="muted"><strong>开始：</strong>{{ formatTime(selectedDelegation.started_at) }}</p>
            <p class="muted"><strong>结束：</strong>{{ formatTime(selectedDelegation.finished_at) }}</p>
            <p class="muted"><strong>耗时：</strong>{{ durationLabel(selectedDelegation.started_at, selectedDelegation.finished_at) }}</p>
          </div>
          <pre>{{ selectedDelegation.summary || "暂无摘要。" }}</pre>
        </template>
        <p v-else class="muted">点击左侧节点查看摘要。</p>
      </aside>
    </div>
  </section>

  <section class="panel" v-if="finalOutput">
    <h3>最终答案</h3>
    <pre>{{ finalOutput }}</pre>
  </section>

  <section class="panel" v-if="teachingView">
    <h3>教学视图</h3>
    <table>
      <tbody>
        <tr v-if="teachingView.summary"><th>summary</th><td>{{ teachingView.summary }}</td></tr>
        <tr v-if="keyTakeaways.length">
          <th>key_takeaways</th>
          <td>
            <ul class="flat-list">
              <li v-for="item in keyTakeaways" :key="item">{{ item }}</li>
            </ul>
          </td>
        </tr>
      </tbody>
    </table>
  </section>

  <section class="panel" v-if="replay.workspace">
    <h3>Workspace 核心字段</h3>
    <table>
      <tbody>
        <tr><th>user_goal</th><td>{{ replay.workspace.user_goal }}</td></tr>
        <tr><th>project_summary</th><td>{{ replay.workspace.project_summary }}</td></tr>
        <tr><th>latest_patch_summary</th><td>{{ replay.workspace.latest_patch_summary }}</td></tr>
      </tbody>
    </table>
  </section>

  <section class="panel" v-if="replay.execution_log?.length">
    <h3>Execution Log（最近 10 条）</h3>
    <table>
      <thead>
        <tr>
          <th>actor</th>
          <th>action</th>
          <th>status</th>
          <th>message</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in recentLogs" :key="item.event_id || item.id">
          <td>{{ item.actor }}</td>
          <td>{{ item.action }}</td>
          <td>{{ item.status }}</td>
          <td>{{ item.message }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { getRunReplay } from "../api";

const props = defineProps({
  runId: { type: String, required: true },
});

const router = useRouter();
const error = ref("");
const polling = ref(true);
const replay = reactive({
  run: null,
  workspace: null,
  delegations: [],
  execution_log: [],
  teaching_view: null,
});
const selectedDelegationId = ref("");

const recentLogs = computed(() => {
  const logs = Array.isArray(replay.execution_log) ? replay.execution_log : [];
  return logs.slice(-10).reverse();
});

const finalOutput = computed(() => {
  return typeof replay.run?.final_output === "string" ? replay.run.final_output : "";
});

const teachingView = computed(() => {
  return replay.teaching_view && typeof replay.teaching_view === "object" ? replay.teaching_view : null;
});

const keyTakeaways = computed(() => {
  const items = teachingView.value?.key_takeaways;
  return Array.isArray(items) ? items : [];
});
const flowNodes = computed(() => {
  const rows = Array.isArray(replay.delegations) ? replay.delegations : [];
  return rows.map((item, index) => ({
    id: item.delegation_id || item.task_id || `node-${index}`,
    agent: item.target_agent || "unknown",
    status: item.status || "unknown",
    startedAtLabel: formatTime(item.started_at),
  }));
});
const selectedDelegation = computed(() => {
  const rows = Array.isArray(replay.delegations) ? replay.delegations : [];
  if (!rows.length) {
    return null;
  }
  const selected = rows.find(
    (item, index) =>
      (item.delegation_id || item.task_id || `node-${index}`) === selectedDelegationId.value
  );
  return selected || rows[0];
});

let timerId = null;

async function fetchReplay() {
  try {
    error.value = "";
    const data = await getRunReplay(props.runId);
    replay.run = data.run || null;
    replay.workspace = data.workspace || null;
    replay.delegations = data.delegations || [];
    replay.execution_log = data.execution_log || [];
    replay.teaching_view = data.teaching_view || null;
    if (Array.isArray(replay.delegations) && replay.delegations.length) {
      const currentExists = replay.delegations.some(
        (item, index) =>
          (item.delegation_id || item.task_id || `node-${index}`) === selectedDelegationId.value
      );
      if (!selectedDelegationId.value || !currentExists) {
        const failed = replay.delegations.find(
          (item) => String(item.status || "").toLowerCase() === "failed"
        );
        const fallback = failed || replay.delegations[0];
        const fallbackIndex = replay.delegations.indexOf(fallback);
        selectedDelegationId.value = fallback.delegation_id || fallback.task_id || `node-${fallbackIndex}`;
      }
    }
    const status = data.run?.status;
    if (status === "completed" || status === "failed") {
      polling.value = false;
      stopPolling();
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "读取回放失败";
    polling.value = false;
    stopPolling();
  }
}

function startPolling() {
  timerId = setInterval(fetchReplay, 3000);
}

function stopPolling() {
  if (timerId) {
    clearInterval(timerId);
    timerId = null;
  }
}

function goTrace() {
  router.push({ name: "trace", params: { runId: props.runId } });
}

function selectDelegation(id) {
  selectedDelegationId.value = id;
}

function normalizeStatus(status) {
  const s = String(status || "").toLowerCase();
  if (s === "completed") return "completed";
  if (s === "failed") return "failed";
  if (s === "running") return "running";
  return "unknown";
}

function formatTime(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function durationLabel(startedAt, finishedAt) {
  if (!startedAt || !finishedAt) return "—";
  const s = new Date(startedAt).getTime();
  const e = new Date(finishedAt).getTime();
  if (Number.isNaN(s) || Number.isNaN(e) || e < s) return "—";
  const sec = Math.round((e - s) / 1000);
  return `${sec}s`;
}

onMounted(async () => {
  await fetchReplay();
  if (polling.value) {
    startPolling();
  }
});

onBeforeUnmount(() => {
  stopPolling();
});
</script>

<style scoped>
.flow-layout {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.flow-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 8px 0 14px;
}

.flow-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  color: var(--text-secondary, #5c6370);
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.dot-completed { background: #10b981; }
.dot-running { background: #3b82f6; }
.dot-failed { background: #dc2626; }
.dot-unknown { background: #94a3b8; }

.flow-lane {
  overflow-x: auto;
  padding: 8px 0 12px;
}

.flow-chain {
  display: inline-flex;
  align-items: center;
  min-width: max-content;
}

.flow-node-btn {
  border: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
  background: #fff;
  border-radius: 10px;
  padding: 8px 10px;
  min-width: 120px;
  text-align: left;
}

.flow-node-btn.is-selected {
  box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.22);
  transform: translateY(-1px);
}

.flow-node-index {
  display: inline-block;
  font-size: 0.6875rem;
  color: var(--text-muted, #8b929e);
}

.flow-node-agent {
  display: block;
  font-size: 0.8125rem;
  font-weight: 700;
}

.flow-node-status {
  display: block;
  margin-top: 2px;
  font-size: 0.75rem;
  color: var(--text-muted, #8b929e);
}

.flow-node-time {
  display: block;
  margin-top: 3px;
  font-size: 0.6875rem;
  color: var(--text-muted, #8b929e);
}

.flow-node-btn.is-completed {
  border-color: rgba(16, 185, 129, 0.35);
  background: rgba(16, 185, 129, 0.08);
}

.flow-node-btn.is-failed {
  border-color: rgba(220, 38, 38, 0.35);
  background: rgba(220, 38, 38, 0.08);
}

.flow-node-btn.is-running {
  border-color: rgba(59, 130, 246, 0.35);
  background: rgba(59, 130, 246, 0.08);
}

.flow-arrow {
  margin: 0 8px;
  color: var(--text-muted, #8b929e);
}

.flow-detail {
  border: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
  border-radius: 10px;
  padding: 14px 12px;
  background: #fafbfe;
  margin-top: 6px;
}

.flow-detail h4 {
  margin: 0 0 8px;
  font-size: 0.875rem;
}

.flow-detail-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 2px 12px;
  margin-bottom: 6px;
}

</style>
