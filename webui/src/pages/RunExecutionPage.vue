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

  <nav class="run-tabs" aria-label="Run detail tabs">
    <button
      v-for="tab in tabs"
      :key="tab.id"
      type="button"
      class="run-tab"
      :class="{ 'is-active': activeTab === tab.id }"
      @click="activeTab = tab.id"
    >
      <span>{{ tab.label }}</span>
      <small v-if="tab.hint">{{ tab.hint }}</small>
    </button>
  </nav>

  <template v-if="activeTab === 'execution'">
  <section class="panel" v-if="replay.run">
    <h3>运行摘要</h3>
    <table>
      <tbody>
        <tr><th>status</th><td>{{ replay.run.status }}</td></tr>
        <tr><th>session_id</th><td>{{ replay.run.session_id }}</td></tr>
        <tr><th>workdir</th><td>{{ replay.run.workdir || "—" }}</td></tr>
        <tr><th>task</th><td>{{ replay.run.task }}</td></tr>
        <tr><th>model</th><td>{{ replay.run.model }}</td></tr>
        <tr><th>step_count</th><td>{{ replay.run.step_count }}</td></tr>
      </tbody>
    </table>
  </section>

  <section class="panel" v-if="flowNodes.length">
    <h3>执行流程（可视化）</h3>
    <p v-if="flowStepLine" class="flow-step-line muted">{{ flowStepLine }}</p>
    <div class="flow-legend">
      <span class="flow-legend-item"><i class="dot dot-completed" /> 已完成</span>
      <span class="flow-legend-item"><i class="dot dot-running" /> 进行中</span>
      <span class="flow-legend-item"><i class="dot dot-failed" /> 失败</span>
      <span class="flow-legend-item"><i class="dot dot-unknown" /> 未确定</span>
    </div>
    <div class="flow-layout">
      <div
        class="flow-lane"
        tabindex="0"
        role="group"
        :aria-label="'执行流程，共 ' + flowNodes.length + ' 步，方向键可切换节点'"
        @keydown="onFlowKeydown"
      >
        <div class="flow-chain" role="presentation">
          <template v-for="(node, index) in flowNodes" :key="node.id">
            <button
              type="button"
              class="flow-node-btn"
              :class="[
                `is-${normalizeStatus(node.status)}`,
                selectedDelegationId === node.id ? 'is-selected' : '',
              ]"
              :data-node-id="node.id"
              :aria-selected="selectedDelegationId === node.id"
              :ref="(el) => setNodeRef(node.id, el)"
              @click="selectDelegation(node.id)"
            >
              <span class="flow-node-index">#{{ index + 1 }}</span>
              <span class="flow-node-agent">
              <span
                v-if="normalizeStatus(node.status) === 'failed'"
                class="flow-node-fail-mark"
                aria-hidden="true"
                >!</span
              >{{ node.agent }}
            </span>
              <span class="flow-node-status">{{ statusLabel(node.status) }}</span>
              <span class="flow-node-time">{{ node.startedAtLabel }}</span>
            </button>
            <span
              v-if="index < flowNodes.length - 1"
              class="flow-connector"
              aria-hidden="true"
            />
          </template>
        </div>
      </div>
      <aside class="flow-detail">
        <div class="flow-detail-header">
          <h4>节点摘要（只读）</h4>
          <button
            type="button"
            class="btn-secondary btn-compact"
            :disabled="!summaryCopyable"
            @click="copySelectedSummary"
          >
            {{ copyHint }}
          </button>
        </div>
        <template v-if="selectedDelegation">
          <div class="flow-detail-meta">
            <p class="muted"><strong>Agent：</strong>{{ selectedDelegation.target_agent || "—" }}</p>
            <p class="muted">
              <strong>状态：</strong>{{ statusLabel(selectedDelegation.status) }}
            </p>
            <p class="muted"><strong>Step ID：</strong>{{ selectedDelegation.step_id || "—" }}</p>
            <p class="muted"><strong>开始：</strong>{{ formatTime(selectedDelegation.started_at) }}</p>
            <p class="muted"><strong>结束：</strong>{{ formatTime(selectedDelegation.finished_at) }}</p>
            <p class="muted"><strong>耗时：</strong>{{ durationLabel(selectedDelegation.started_at, selectedDelegation.finished_at) }}</p>
          </div>
          <pre class="flow-detail-pre">{{ selectedDelegation.summary || "暂无摘要。" }}</pre>
        </template>
        <p v-else class="muted">点击上方流程中的节点查看摘要；焦点在流程区域时可用 ← → 或 ↑ ↓ 切换。</p>
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

  <template v-else-if="activeTab === 'memory'">
    <section class="panel memory-panel" v-if="replay.workspace">
      <div class="memory-panel-head">
        <div>
          <h3>Memory / Workspace</h3>
          <p class="muted">
            只读展示本次运行的 shared workspace、各 Agent private memory、artifact 索引与上下文治理信息。
          </p>
        </div>
        <div class="memory-stats">
          <span class="memory-stat"><strong>{{ privateMemoryEntries.length }}</strong> private contexts</span>
          <span class="memory-stat"><strong>{{ artifactsIndex.length }}</strong> artifacts</span>
          <span class="memory-stat"><strong>{{ executionNotes.length }}</strong> notes</span>
          <span class="memory-stat" :class="plannerRagShortcutApplied === true ? 'is-positive' : 'is-neutral'">
            <strong>RAG shortcut</strong> {{ plannerRagShortcutLabel }}
          </span>
        </div>
      </div>

      <div class="memory-grid">
        <article class="memory-card">
          <h4>Shared Workspace</h4>
          <table class="memory-table">
            <tbody>
              <tr v-for="row in sharedWorkspaceRows" :key="row.key">
                <th>{{ row.key }}</th>
                <td>{{ row.value }}</td>
              </tr>
            </tbody>
          </table>
        </article>

        <article class="memory-card">
          <h4>Memory Policy / Context Builder</h4>
          <p class="muted">
            当前展示的是运行时落入 workspace 的策略快照与上下文治理线索；用于确认“哪些状态会进入不同 Agent 的上下文”。
          </p>
          <JsonBlock :data="memoryPolicyView" />
        </article>
      </div>

      <section class="memory-section">
        <div class="memory-section-title">
          <h4>Agent Private Memory</h4>
          <span class="muted">按 Agent 分区保存，避免所有 Agent 共享全量历史。</span>
        </div>
        <div v-if="privateMemoryEntries.length" class="private-memory-grid">
          <article
            v-for="entry in privateMemoryEntries"
            :key="entry.agentId"
            class="private-memory-card"
          >
            <div class="private-memory-head">
              <span class="agent-chip">{{ entry.agentId }}</span>
              <span class="muted">{{ entry.fieldCount }} fields</span>
            </div>
            <JsonBlock :data="entry.payload" />
          </article>
        </div>
        <p v-else class="muted">暂无 private context。</p>
      </section>

      <section class="memory-section">
        <div class="memory-section-title">
          <h4>Artifacts Index</h4>
          <span class="muted">Workspace 中登记的 plan / analysis / patch / review 等工件索引。</span>
        </div>
        <table v-if="artifactsIndex.length">
          <thead>
            <tr>
              <th>key</th>
              <th>type</th>
              <th>version</th>
              <th>summary</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="artifact in artifactsIndex" :key="`${artifact.key}-${artifact.version}`">
              <td>{{ artifact.key }}</td>
              <td>{{ artifact.type }}</td>
              <td>{{ artifact.version }}</td>
              <td>{{ artifact.summary }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted">暂无 artifact 索引。</p>
      </section>

      <section class="memory-section">
        <div class="memory-section-title">
          <h4>Execution Notes</h4>
          <span class="muted">Orchestrator 写入 workspace 的执行备注。</span>
        </div>
        <ol v-if="executionNotes.length" class="memory-notes">
          <li v-for="(note, index) in executionNotes" :key="`${index}-${note}`">{{ note }}</li>
        </ol>
        <p v-else class="muted">暂无 execution notes。</p>
      </section>
    </section>

    <section v-else class="panel">
      <h3>Memory / Workspace</h3>
      <p class="muted">当前 run 没有可展示的 workspace 快照。</p>
    </section>
  </template>
</template>

<script setup>
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import { useRouter } from "vue-router";
import { getRunReplay } from "../api";
import JsonBlock from "../components/JsonBlock.vue";

const props = defineProps({
  runId: { type: String, required: true },
});

const router = useRouter();
const error = ref("");
const polling = ref(true);
const activeTab = ref("execution");
const replay = reactive({
  run: null,
  workspace: null,
  delegations: [],
  execution_log: [],
  teaching_view: null,
  artifacts: [],
});
const selectedDelegationId = ref("");
const nodeEls = ref(new Map());
const copyHint = ref("复制摘要");

const tabs = computed(() => [
  {
    id: "execution",
    label: "Execution",
    hint: replay.delegations?.length ? `${replay.delegations.length} delegations` : "",
  },
  {
    id: "memory",
    label: "Memory / Workspace",
    hint: replay.workspace ? `${privateMemoryEntries.value.length} agents` : "",
  },
]);

function setNodeRef(id, el) {
  if (el) {
    nodeEls.value.set(id, el);
  } else {
    nodeEls.value.delete(id);
  }
}

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
const workspace = computed(() => {
  return replay.workspace && typeof replay.workspace === "object" ? replay.workspace : null;
});
const artifactsIndex = computed(() => {
  const items = workspace.value?.artifacts_index;
  return Array.isArray(items) ? items : [];
});
const executionNotes = computed(() => {
  const items = workspace.value?.execution_notes;
  return Array.isArray(items) ? items : [];
});
const privateContext = computed(() => {
  const value = workspace.value?.private_context;
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
});
const privateMemoryEntries = computed(() => {
  return Object.entries(privateContext.value)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([agentId, payload]) => ({
      agentId,
      payload,
      fieldCount: payload && typeof payload === "object" && !Array.isArray(payload)
        ? Object.keys(payload).length
        : 0,
    }));
});
const sharedWorkspaceRows = computed(() => {
  const ws = workspace.value || {};
  return [
    { key: "user_goal", value: compactText(ws.user_goal) },
    { key: "current_plan", value: ws.current_plan?.steps ? `${ws.current_plan.steps.length} steps` : "—" },
    { key: "project_summary", value: compactText(ws.project_summary) },
    { key: "latest_patch_summary", value: compactText(ws.latest_patch_summary) },
    {
      key: "latest_test_result",
      value: ws.latest_test_result
        ? `${ws.latest_test_result.status || "unknown"} · ${compactText(ws.latest_test_result.summary)}`
        : "—",
    },
    { key: "artifacts_index", value: `${artifactsIndex.value.length} items` },
    { key: "execution_notes", value: `${executionNotes.value.length} notes` },
  ];
});
const memoryPolicyView = computed(() => {
  const orchestrator = privateContext.value.orchestrator || {};
  const planMetadata = workspace.value?.current_plan?.metadata || {};
  return {
    policy: orchestrator.policy || null,
    strategy_profile: orchestrator.strategy_profile || null,
    plan_strategy: planMetadata.planner_strategy || null,
    context_builder: {
      shared_workspace_fields: [
        "user_goal",
        "current_plan",
        "project_summary",
        "latest_patch_summary",
        "latest_test_result",
        "artifacts_index",
        "execution_notes",
      ],
      private_memory_agents: privateMemoryEntries.value.map((item) => item.agentId),
      note: "具体 prompt 装配由 ContextBuilder 按 agent 类型选择性读取 workspace/private_context。",
    },
  };
});
const plannerRagShortcutApplied = computed(() => {
  const planMetadata = workspace.value?.current_plan?.metadata || {};
  const plannerStrategy = planMetadata.planner_strategy || {};
  return typeof plannerStrategy.rag_shortcut_applied === "boolean"
    ? plannerStrategy.rag_shortcut_applied
    : null;
});
const plannerRagShortcutLabel = computed(() => {
  if (plannerRagShortcutApplied.value === true) {
    return "ON";
  }
  if (plannerRagShortcutApplied.value === false) {
    return "OFF";
  }
  return "N/A";
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
const flowStepLine = computed(() => {
  const n = flowNodes.value.length;
  if (!n) {
    return "";
  }
  const i = flowNodes.value.findIndex((node) => node.id === selectedDelegationId.value);
  const k = i >= 0 ? i + 1 : 1;
  return `共 ${n} 步 · 当前第 ${k} 步`;
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
const summaryCopyable = computed(() => {
  const t = selectedDelegation.value?.summary;
  return typeof t === "string" && t.length > 0;
});

let timerId = null;

function scrollSelectedNodeIntoView() {
  const el = nodeEls.value.get(selectedDelegationId.value);
  if (el && typeof el.scrollIntoView === "function") {
    el.scrollIntoView({ block: "nearest", inline: "nearest" });
  }
}

watch(
  () => [selectedDelegationId.value, flowNodes.value.length],
  () => {
    void nextTick(() => {
      scrollSelectedNodeIntoView();
    });
  },
  { flush: "post" }
);

async function fetchReplay() {
  try {
    error.value = "";
    const data = await getRunReplay(props.runId);
    replay.run = data.run || null;
    replay.workspace = data.workspace || null;
    replay.delegations = data.delegations || [];
    replay.execution_log = data.execution_log || [];
    replay.teaching_view = data.teaching_view || null;
    replay.artifacts = data.artifacts || [];
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

function onFlowKeydown(e) {
  const keys = ["ArrowLeft", "ArrowUp", "ArrowRight", "ArrowDown"];
  if (!keys.includes(e.key)) {
    return;
  }
  const list = flowNodes.value;
  if (list.length === 0) {
    return;
  }
  let idx = list.findIndex((n) => n.id === selectedDelegationId.value);
  if (idx < 0) {
    idx = 0;
  }
  if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
    e.preventDefault();
    if (idx > 0) {
      selectDelegation(list[idx - 1].id);
    }
  } else if (e.key === "ArrowRight" || e.key === "ArrowDown") {
    e.preventDefault();
    if (idx < list.length - 1) {
      selectDelegation(list[idx + 1].id);
    }
  }
}

async function copySelectedSummary() {
  const text = selectedDelegation.value?.summary;
  if (typeof text !== "string" || !text.length) {
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    copyHint.value = "已复制";
    window.setTimeout(() => {
      copyHint.value = "复制摘要";
    }, 2000);
  } catch {
    copyHint.value = "复制失败";
    window.setTimeout(() => {
      copyHint.value = "复制摘要";
    }, 2000);
  }
}

function normalizeStatus(status) {
  const s = String(status || "").toLowerCase();
  if (s === "completed") return "completed";
  if (s === "failed") return "failed";
  if (s === "running") return "running";
  return "unknown";
}

function statusLabel(status) {
  const key = normalizeStatus(status);
  if (key === "completed") {
    return "已完成";
  }
  if (key === "failed") {
    return "失败";
  }
  if (key === "running") {
    return "进行中";
  }
  const raw = String(status || "").trim();
  return raw && raw.toLowerCase() !== "unknown" ? raw : "未确定";
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

function compactText(value, maxLength = 180) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  const text = typeof value === "string" ? value : JSON.stringify(value);
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength)}…`;
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
.run-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: -6px 0 20px;
}

.run-tab {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 42px;
  padding: 9px 14px;
  border: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
  background: rgba(255, 255, 255, 0.72);
  color: var(--text-secondary, #5c6370);
  box-shadow: 0 1px 2px rgba(15, 20, 25, 0.03);
}

.run-tab small {
  color: var(--text-muted, #8b929e);
  font-size: 0.7rem;
  font-weight: 700;
}

.run-tab.is-active {
  background:
    linear-gradient(135deg, rgba(79, 70, 229, 0.14), rgba(13, 148, 136, 0.08)),
    #fff;
  color: var(--accent-text, #4338ca);
  border-color: rgba(79, 70, 229, 0.28);
  box-shadow: 0 6px 22px rgba(79, 70, 229, 0.12);
}

.memory-panel {
  background:
    radial-gradient(circle at 0 0, rgba(79, 70, 229, 0.08), transparent 34%),
    radial-gradient(circle at 100% 6%, rgba(13, 148, 136, 0.08), transparent 30%),
    var(--bg-elevated, #fff);
}

.memory-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.memory-panel-head h3 {
  margin-bottom: 6px;
}

.memory-stats {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  min-width: 220px;
}

.memory-stat {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 7px 10px;
  border: 1px solid rgba(79, 70, 229, 0.18);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.78);
  color: var(--text-secondary, #5c6370);
  font-size: 0.75rem;
}

.memory-stat strong {
  color: var(--text-primary, #1a1d26);
}

.memory-stat.is-positive {
  border-color: rgba(16, 185, 129, 0.35);
  background: rgba(16, 185, 129, 0.08);
}

.memory-stat.is-neutral {
  border-color: rgba(100, 116, 139, 0.28);
}

.memory-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr);
  gap: 14px;
  margin-bottom: 18px;
}

.memory-card,
.private-memory-card,
.memory-section {
  border: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 1px 2px rgba(15, 20, 25, 0.03);
}

.memory-card {
  padding: 14px;
  min-width: 0;
}

.memory-card h4,
.memory-section h4 {
  margin: 0 0 10px;
  font-size: 0.92rem;
}

.memory-card :deep(pre),
.private-memory-card :deep(pre) {
  max-height: 360px;
  margin: 10px 0 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.memory-table tbody th {
  width: 34%;
}

.memory-section {
  padding: 14px;
  margin-top: 14px;
}

.memory-section-title {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.private-memory-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.private-memory-card {
  min-width: 0;
  padding: 12px;
}

.private-memory-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.agent-chip {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: #0f172a;
  color: #f8fafc;
  font-size: 0.75rem;
  font-weight: 800;
  letter-spacing: 0.02em;
}

.memory-notes {
  margin: 0;
  padding-left: 1.35rem;
  color: var(--text-primary, #1a1d26);
}

.memory-notes li + li {
  margin-top: 6px;
}

.flow-step-line {
  margin: 0 0 8px;
  font-size: 0.8125rem;
}

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
  border-radius: 8px;
  outline: none;
}
.flow-lane:focus-visible {
  box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.25);
}

.flow-chain {
  display: inline-flex;
  flex-direction: row;
  flex-wrap: nowrap;
  align-items: center;
  min-width: min-content;
  width: 100%;
}

.flow-node-fail-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1rem;
  height: 1rem;
  margin-right: 4px;
  border-radius: 50%;
  background: #dc2626;
  color: #fff;
  font-size: 0.65rem;
  font-weight: 800;
  line-height: 1;
  vertical-align: middle;
}

.flow-node-btn {
  border: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
  background: #fff;
  border-radius: 10px;
  padding: 8px 10px;
  min-width: 120px;
  flex: 0 0 auto;
  text-align: left;
  align-self: center;
  cursor: pointer;
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
  border: 2px solid rgba(220, 38, 38, 0.65);
  background: rgba(220, 38, 38, 0.12);
  box-shadow: inset 0 0 0 1px rgba(220, 38, 38, 0.1);
}

.flow-node-btn.is-running {
  border-color: rgba(59, 130, 246, 0.35);
  background: rgba(59, 130, 246, 0.08);
}

.flow-connector {
  flex: 0 0 1.25rem;
  height: 2px;
  align-self: center;
  background: var(--border-subtle, rgba(15, 20, 25, 0.18));
  border-radius: 1px;
  opacity: 0.9;
}

.flow-detail {
  border: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
  border-radius: 10px;
  padding: 14px 12px;
  background: #fafbfe;
  margin-top: 6px;
}

.flow-detail-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.flow-detail h4 {
  margin: 0;
  font-size: 0.875rem;
}

.btn-compact {
  padding: 4px 10px;
  font-size: 0.75rem;
  flex-shrink: 0;
}

.flow-detail-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 2px 12px;
  margin-bottom: 6px;
}

.flow-detail-pre {
  max-height: 40vh;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 窄屏：竖向时间轴，少横滑 */
@media (max-width: 640px) {
  .memory-panel-head,
  .memory-grid {
    grid-template-columns: 1fr;
    flex-direction: column;
  }
  .memory-stats {
    justify-content: flex-start;
    min-width: 0;
  }
  .private-memory-grid {
    grid-template-columns: 1fr;
  }
  .flow-lane {
    overflow-x: visible;
    padding: 8px 0 4px;
  }
  .flow-chain {
    flex-direction: column;
    align-items: stretch;
    min-width: 0;
    max-width: 100%;
  }
  .flow-node-btn {
    width: 100%;
    max-width: 100%;
    min-width: 0;
  }
  .flow-connector {
    flex: none;
    width: 2px;
    height: 0.5rem;
    margin: 0 auto;
  }
  .flow-detail-meta {
    grid-template-columns: 1fr;
  }
}

</style>
