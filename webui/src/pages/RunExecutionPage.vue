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
              <span class="flow-node-agent">{{ node.agent }}</span>
              <span class="flow-node-status">{{ node.status || "unknown" }}</span>
            </button>
            <span v-if="index < flowNodes.length - 1" class="flow-arrow">→</span>
          </template>
        </div>
      </div>
      <aside class="flow-detail">
        <h4>节点摘要（只读）</h4>
        <template v-if="selectedDelegation">
          <p class="muted"><strong>Agent：</strong>{{ selectedDelegation.target_agent || "—" }}</p>
          <p class="muted"><strong>状态：</strong>{{ selectedDelegation.status || "—" }}</p>
          <p class="muted"><strong>Step ID：</strong>{{ selectedDelegation.step_id || "—" }}</p>
          <p class="muted"><strong>开始：</strong>{{ selectedDelegation.started_at || "—" }}</p>
          <p class="muted"><strong>结束：</strong>{{ selectedDelegation.finished_at || "—" }}</p>
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
    if (!selectedDelegationId.value && Array.isArray(replay.delegations) && replay.delegations.length) {
      const first = replay.delegations[0];
      selectedDelegationId.value = first.delegation_id || first.task_id || "node-0";
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
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr);
  gap: 14px;
}

.flow-lane {
  overflow-x: auto;
  padding-bottom: 6px;
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
  padding: 10px 12px;
  background: #fafbfe;
}

.flow-detail h4 {
  margin: 0 0 8px;
  font-size: 0.875rem;
}

@media (max-width: 980px) {
  .flow-layout {
    grid-template-columns: 1fr;
  }
}
</style>
