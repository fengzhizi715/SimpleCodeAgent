<template>
  <section class="panel autonomy-hero">
    <div>
      <h2>Autonomy Runtime</h2>
      <p class="muted autonomy-lead">
        作为 `v3` 的系统视角入口，这里集中观察最近运行的 graph、event 与 trigger，
        不替代任务详情，只负责帮助我们跨运行理解 runtime 行为。
      </p>
    </div>
    <div class="autonomy-hero-actions">
      <button class="btn-secondary btn-sm" :disabled="loading" @click="loadAutonomy">
        {{ loading ? "刷新中…" : "刷新 Runtime" }}
      </button>
      <span class="muted">最近刷新：{{ lastUpdatedText }}</span>
    </div>
  </section>

  <p v-if="error" class="error">{{ error }}</p>

  <section class="panel autonomy-toolbar">
    <div class="autonomy-toolbar-main">
      <label class="autonomy-field">
        <span>观察 Run</span>
        <select v-model="selectedRunId">
          <option v-for="run in recentV3Runs" :key="run.run_id" :value="run.run_id">
            {{ formatRunOption(run) }}
          </option>
        </select>
      </label>
      <div class="autonomy-toolbar-links" v-if="selectedRunId">
        <RouterLink :to="{ name: 'execution', params: { runId: selectedRunId }, query: { version: 'v3' } }">
          查看任务详情
        </RouterLink>
        <RouterLink :to="{ name: 'trace', params: { runId: selectedRunId }, query: { version: 'v3' } }">
          查看 Trace
        </RouterLink>
      </div>
    </div>
    <div class="autonomy-toolbar-side">
      <span class="badge">最近 V3 Runs {{ recentV3Runs.length }}</span>
      <span v-if="selectedRun?.status" class="badge autonomy-status-badge" :class="statusClass(selectedRun.status)">
        {{ statusLabel(selectedRun.status) }}
      </span>
    </div>
  </section>

  <section class="panel autonomy-filter-panel">
    <div class="autonomy-filter-grid">
      <label class="autonomy-field">
        <span>Event Type</span>
        <select v-model="selectedEventType">
          <option value="">全部事件类型</option>
          <option v-for="eventType in eventTypeOptions" :key="eventType" :value="eventType">
            {{ eventType }}
          </option>
        </select>
      </label>
      <label class="autonomy-field">
        <span>Trigger Rule</span>
        <select v-model="selectedTriggerRule">
          <option value="">全部 Trigger Rules</option>
          <option v-for="rule in triggerRuleOptions" :key="rule" :value="rule">
            {{ rule }}
          </option>
        </select>
      </label>
      <div class="autonomy-filter-actions">
        <button class="btn-secondary btn-sm" :disabled="!hasActiveFilters" @click="clearFilters">
          清空过滤
        </button>
      </div>
    </div>
    <div v-if="hasActiveFilters" class="autonomy-active-filters">
      <span class="badge">run_id: {{ shortChainId(selectedRunId) }}</span>
      <span v-if="selectedEventType" class="badge">event_type: {{ selectedEventType }}</span>
      <span v-if="selectedTriggerRule" class="badge">trigger_rule: {{ selectedTriggerRule }}</span>
    </div>
  </section>

  <section class="autonomy-stat-grid">
    <article v-for="card in overviewCards" :key="card.label" class="panel autonomy-stat-card">
      <span>{{ card.label }}</span>
      <strong>{{ card.value }}</strong>
      <small>{{ card.help }}</small>
    </article>
  </section>

  <section class="panel" v-if="selectedRun">
    <div class="autonomy-run-head">
      <div>
        <h3>{{ selectedRun.task || "未命名任务" }}</h3>
        <p class="muted">
          run_id: <code>{{ selectedRun.run_id }}</code>
        </p>
      </div>
      <div class="autonomy-run-meta">
        <span><strong>Model:</strong> {{ selectedRun.model || "—" }}</span>
        <span><strong>规划模式:</strong> {{ planning?.planning_mode || "rule_based" }}</span>
        <span><strong>更新时间:</strong> {{ formatTime(selectedRun.updated_at) }}</span>
      </div>
    </div>
  </section>

  <nav class="run-tabs autonomy-tabs" aria-label="Autonomy runtime tabs">
    <button
      v-for="tab in tabs"
      :key="tab.id"
      type="button"
      class="run-tab-btn"
      :class="{ 'is-active': activeTab === tab.id }"
      @click="activeTab = tab.id"
    >
      <span>{{ tab.label }}</span>
      <small v-if="tab.hint">{{ tab.hint }}</small>
    </button>
  </nav>

  <section class="panel" v-if="activeTab === 'overview'">
    <div class="autonomy-section-head">
      <div>
        <h3>Overview</h3>
        <p class="muted">先看最近的 v3 运行，再决定是否下钻到 graph、events 或 triggers。</p>
      </div>
    </div>
    <div class="autonomy-overview-layout">
      <div class="autonomy-overview-answer">
        <h4>当前 Run 摘要</h4>
        <p class="autonomy-summary">{{ selectedRunSummary }}</p>
        <div class="autonomy-highlight-list" v-if="overviewHighlights.length">
          <span v-for="item in overviewHighlights" :key="item" class="badge">{{ item }}</span>
        </div>
        <div class="autonomy-highlight-list" v-if="demoScenarios.length" style="margin-top: 12px">
          <span v-for="item in demoScenarios" :key="item" class="badge">{{ item }}</span>
        </div>
        <div class="autonomy-overview-runtime" v-if="runtimeSummary.run_mode" style="margin-top: 14px">
          <strong>{{ runtimeSummary.run_mode.label }}</strong>
          <p class="muted">{{ runtimeSummary.run_mode.description }}</p>
        </div>
      </div>
      <div class="autonomy-overview-list">
        <h4>最近 V3 运行</h4>
        <table v-if="recentV3Runs.length">
          <thead>
            <tr>
              <th>任务</th>
              <th>状态</th>
              <th>更新时间</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="run in recentV3Runs.slice(0, 8)"
              :key="run.run_id"
              :class="{ 'is-selected-row': run.run_id === selectedRunId }"
              @click="selectedRunId = run.run_id"
            >
              <td>{{ compactText(run.task, 60) }}</td>
              <td><span class="badge autonomy-status-badge" :class="statusClass(run.status)">{{ statusLabel(run.status) }}</span></td>
              <td>{{ formatTime(run.updated_at) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted">暂无 v3 运行记录。</p>
      </div>
    </div>
    <div class="autonomy-demo-grid" style="margin-top: 18px">
      <article v-for="demo in demoCatalog" :key="demo.id" class="planning-node-card">
        <div class="planning-node-head">
          <h4>{{ demo.title }}</h4>
          <p class="muted">{{ demo.goal }}</p>
        </div>
        <p class="autonomy-node-summary">{{ demo.prompt }}</p>
        <p class="planning-node-deps muted">看点：{{ demo.watch }}</p>
        <div class="autonomy-demo-actions">
          <button class="btn-secondary btn-sm" :disabled="demoLaunchingId === demo.id" @click="launchRecoveryDemo(demo)">
            {{ demoLaunchingId === demo.id ? "启动中…" : demo.actionLabel }}
          </button>
          <button class="btn-secondary btn-sm" :disabled="!demo.latestRunId" @click="openDemoRun(demo)">
            打开最近一次 Run
          </button>
          <button class="btn-secondary btn-sm" :disabled="!demo.latestRunId || replayCompareLoading" @click="openReplayCompare(demo)">
            {{ replayCompareLoading && replayCompareDemoId === demo.id ? "对照中…" : "Replay Compare" }}
          </button>
        </div>
        <p v-if="demo.latestRunId" class="muted autonomy-inline-note">
          最近运行：{{ shortChainId(demo.latestRunId) }} · {{ demo.latestStatusLabel }}
        </p>
      </article>
    </div>
    <section class="autonomy-replay-panel" style="margin-top: 18px">
      <div class="autonomy-section-head">
        <div>
          <h3>Recovery Demos</h3>
          <p class="muted">固定展示 recovery success / failure demo 的最近状态，并保留 replay 对照入口。</p>
        </div>
      </div>
      <div class="autonomy-stat-grid" v-if="recoveryStatusCards.length">
        <article v-for="card in recoveryStatusCards" :key="card.label" class="panel autonomy-stat-card">
          <span>{{ card.label }}</span>
          <strong>{{ card.value }}</strong>
          <small>{{ card.help }}</small>
        </article>
      </div>
      <div class="planning-node-card" v-if="replayCompareState.runId || replayCompareError">
        <div class="planning-node-head">
          <h4>Replay Compare</h4>
          <p class="muted">{{ replayCompareState.demoTitle || "对 demo recovery 链执行 replay，并和原始 run 做最小对照。" }}</p>
        </div>
        <p v-if="replayCompareError" class="error">{{ replayCompareError }}</p>
        <template v-else-if="replayCompareState.runId">
          <p class="planning-node-deps muted">
            run: {{ shortChainId(replayCompareState.runId) }} ·
            target: {{ replayCompareState.targetSkillName || "—" }} ·
            replay: {{ replayCompareState.replaySuccess ? "success" : "failed" }}
          </p>
          <p class="autonomy-node-summary">{{ replayCompareState.summary || "暂无 replay 结果。" }}</p>
          <p class="muted autonomy-inline-note">{{ replayCompareState.originalSummary || "—" }}</p>
        </template>
      </div>
    </section>
  </section>

  <section class="panel" v-if="activeTab === 'runtime'">
    <div class="autonomy-section-head">
      <div>
        <h3>Runtime Status</h3>
        <p class="muted">这里优先回答这次运行到底进入了哪种 runtime 模式，以及 governance 是怎么作用的。</p>
      </div>
    </div>
    <div class="autonomy-stat-grid">
      <article v-for="card in runtimeStatusCards" :key="card.label" class="panel autonomy-stat-card">
        <span>{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
        <small>{{ card.help }}</small>
      </article>
    </div>
    <div v-if="flowCards.length" class="planning-node-list" style="margin-top: 16px">
      <article v-for="card in flowCards" :key="`${card.trigger_rule_id}-${card.source_event_id || card.event_type}`" class="planning-node-card">
        <div class="planning-node-top">
          <div class="planning-node-title">
            <span class="planning-node-index">{{ card.event_type }}</span>
            <strong>{{ card.trigger_rule_id }}</strong>
          </div>
          <span class="badge autonomy-status-badge" :class="card.result_label === 'Executed' ? 'badge-ok' : 'badge-warn'">
            {{ card.result_label }}
          </span>
        </div>
        <p class="planning-node-deps muted">follow-up: {{ card.follow_up_label }}</p>
        <p class="planning-node-deps muted">governance: {{ card.governance_label }}</p>
        <p class="autonomy-node-summary">{{ card.summary || card.stop_reason || "No additional summary." }}</p>
      </article>
    </div>
    <table v-if="governanceExplainItems.length" style="margin-top: 16px">
      <thead>
        <tr>
          <th>Status</th>
          <th>Rule</th>
          <th>Event</th>
          <th>Reason</th>
          <th>Detail</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in governanceExplainItems" :key="`${item.rule_id || 'none'}-${item.event_type || 'event'}-${item.label}`">
          <td>{{ item.label }}</td>
          <td>{{ item.rule_id || "—" }}</td>
          <td>{{ item.event_type || "—" }}</td>
          <td>{{ item.reason }}</td>
          <td>{{ item.detail || "—" }}</td>
        </tr>
      </tbody>
    </table>
  </section>

  <section class="panel" v-if="activeTab === 'graph'">
    <div class="autonomy-section-head">
      <div>
        <h3>Graph</h3>
        <p class="muted">保留任务详情里的结果优先结构，这里只强调 graph 模板、分层和节点执行面。</p>
      </div>
      <span class="badge">{{ graphNodes.length }} nodes</span>
    </div>
    <table v-if="planning">
      <tbody>
        <tr><th>goal_kind</th><td>{{ planning.goal_kind || "—" }}</td></tr>
        <tr><th>repo_profile</th><td>{{ planning.repo_profile || "—" }}</td></tr>
        <tr><th>template</th><td>{{ planning.template_name || "—" }}</td></tr>
        <tr><th>recovery_strategy</th><td>{{ planning.recovery_strategy || "—" }}</td></tr>
        <tr><th>execution_layers</th><td>{{ formatExecutionLayers(planning.execution_layers) }}</td></tr>
      </tbody>
    </table>
    <p v-if="planning?.template_reason" class="muted autonomy-panel-note">{{ planning.template_reason }}</p>
    <div v-if="graphSections.length" class="autonomy-graph-sections">
      <div v-for="section in graphSections" :key="section.id" class="planning-node-section">
        <div class="planning-node-head">
          <h4>{{ section.label }}</h4>
          <p class="muted">{{ section.description }}</p>
        </div>
        <div class="planning-node-list">
          <article v-for="node in section.nodes" :key="node.node_id" class="planning-node-card">
            <div class="planning-node-top">
              <div class="planning-node-title">
                <span class="planning-node-index">{{ node.node_id }}</span>
                <strong>{{ node.skill_name || "unknown skill" }}</strong>
              </div>
              <span class="badge autonomy-status-badge" :class="statusClass(node.status)">
                {{ statusLabel(node.status) }}
              </span>
            </div>
            <p class="muted planning-node-deps">
              deps: {{ Array.isArray(node.dependencies) && node.dependencies.length ? node.dependencies.join(", ") : "—" }}
            </p>
            <p class="autonomy-node-summary">{{ node.summary || "暂无摘要" }}</p>
          </article>
        </div>
      </div>
    </div>
    <p v-else class="muted">当前 run 暂无 graph 节点可展示。</p>
  </section>

  <section class="panel" v-if="activeTab === 'events'">
    <div class="autonomy-section-head">
      <div>
        <h3>Events</h3>
        <p class="muted">从单次 run 中抽出 event 视角；点任意事件可展开它的 execution chain。</p>
      </div>
      <span class="badge">{{ filteredEventRows.length }}/{{ eventRows.length }} items</span>
    </div>
    <div class="autonomy-events-layout" v-if="filteredEventRows.length">
      <div class="autonomy-events-list">
        <button
          v-for="item in filteredEventRows"
          :key="item.event_id || `${item.timestamp}-${item.event_type}`"
          type="button"
          class="autonomy-event-row"
          :class="{
            'is-selected': selectedEventId === item.event_id,
            'is-disabled': !canInspectEventChain(item),
          }"
          :disabled="!canInspectEventChain(item)"
          :title="canInspectEventChain(item) ? '查看 event chain' : '无法展开 event chain'"
          @click="inspectEventChain(item)"
        >
          <div class="autonomy-event-row-head">
            <strong>{{ item.event_type || item.type || "event" }}</strong>
            <span>{{ formatTime(item.timestamp || item.ts || item.created_at) }}</span>
          </div>
          <div class="autonomy-event-row-meta">
            <span>{{ item.source || "unknown" }}</span>
            <span>{{ compactText(summarizeV3Event(item), 100) }}</span>
          </div>
          <div class="autonomy-event-row-foot">
            <span class="badge" :class="canInspectEventChain(item) ? 'badge-enabled' : 'badge-disabled'">
              {{ canInspectEventChain(item) ? "可展开 chain" : "无 chain" }}
            </span>
          </div>
        </button>
      </div>
      <aside class="autonomy-events-panel">
        <div class="autonomy-events-panel-head">
          <div>
            <h4>Execution Chain</h4>
            <p class="muted">
              {{ eventChain?.execution_chain_id ? shortChainId(eventChain.execution_chain_id) : "选择左侧事件后查看" }}
            </p>
          </div>
        </div>
        <p v-if="eventError" class="error">{{ eventError }}</p>
        <template v-else-if="eventLoading">
          <p class="muted">读取事件链中…</p>
        </template>
        <template v-else-if="eventChain">
          <div class="autonomy-chain-meta">
            <span><strong>root_event:</strong> {{ eventChain.root_event_type || "—" }}</span>
            <span><strong>items:</strong> {{ eventChain.item_count || 0 }}</span>
          </div>
          <pre class="autonomy-chain-view">{{ eventChainView || "暂无可读视图。" }}</pre>
        </template>
        <template v-else>
          <p class="muted">选择一条事件后，这里会展示对应的 event chain。</p>
        </template>
      </aside>
    </div>
    <p v-else class="muted">当前过滤条件下没有事件记录。</p>
  </section>

  <section class="panel" v-if="activeTab === 'triggers'">
    <div class="autonomy-section-head">
      <div>
        <h3>Triggers</h3>
        <p class="muted">这里聚焦规则命中、跳过与当前启停状态，适合作为 runtime 治理视图。</p>
      </div>
      <span class="badge">{{ filteredTriggerRules.length }}/{{ triggerRules.length }} rules</span>
    </div>
    <table v-if="filteredTriggerRules.length">
      <thead>
        <tr>
          <th>Rule</th>
          <th>When</th>
          <th>Target</th>
          <th>State</th>
          <th>Hit Counts</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="rule in filteredTriggerRules" :key="rule.rule_id">
          <td>
            <strong>{{ rule.rule_id }}</strong>
            <p class="muted autonomy-inline-note">{{ compactText(rule.description || "", 80) }}</p>
          </td>
          <td>{{ rule.event_type || "—" }}</td>
          <td>{{ rule.target_skill_name || "—" }}</td>
          <td>
            <span class="badge" :class="isRuleEnabled(rule.rule_id) ? 'badge-enabled' : 'badge-disabled'">
              {{ isRuleEnabled(rule.rule_id) ? "enabled" : "disabled" }}
            </span>
          </td>
          <td>
            {{ triggerHitSummary(rule.rule_id) }}
          </td>
          <td>
            <button
              class="btn-secondary btn-sm"
              :disabled="togglingRuleId === rule.rule_id"
              @click="toggleRule(rule.rule_id)"
            >
              {{ togglingRuleId === rule.rule_id ? "更新中…" : isRuleEnabled(rule.rule_id) ? "临时禁用" : "重新启用" }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">当前过滤条件下没有 trigger rules。</p>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import {
  getRunDetail,
  getV3EventChain,
  getV3EventChainView,
  getV3RunReplayPlan,
  getV3TriggerHitCounts,
  getV3TriggerRuleStates,
  listRuns,
  replayV3EventChain,
  runV3RecoveryDemo,
  setV3TriggerRuleEnabled,
} from "../api";
import { formatGovernanceCount, normalizeV3RuntimeSummary } from "../v3RuntimeSummary";

const route = useRoute();
const router = useRouter();

const loading = ref(false);
const error = ref("");
const lastUpdatedAt = ref(null);
const recentV3Runs = ref([]);
const selectedRunId = ref(String(route.query.run_id || ""));
const selectedDetail = ref(null);
const triggerStateOverrides = ref({});
const triggerHitCounts = ref([]);
const activeTab = ref(String(route.query.tab || "overview"));
const selectedEventType = ref(String(route.query.event_type || "").trim());
const selectedTriggerRule = ref(String(route.query.trigger_rule || "").trim());
const eventLoading = ref(false);
const eventError = ref("");
const eventChain = ref(null);
const eventChainView = ref("");
const selectedEventId = ref("");
const togglingRuleId = ref("");
const demoRunDetails = ref({});
const demoLaunchingId = ref("");
const replayCompareLoading = ref(false);
const replayCompareDemoId = ref("");
const replayCompareError = ref("");
const replayCompareState = ref({
  runId: "",
  demoTitle: "",
  targetSkillName: "",
  summary: "",
  originalSummary: "",
  replaySuccess: false,
});

const selectedRun = computed(() => {
  if (!selectedRunId.value) return null;
  return recentV3Runs.value.find((run) => run.run_id === selectedRunId.value) || selectedDetail.value?.run || null;
});
const runtimeSummary = computed(() => normalizeV3RuntimeSummary(selectedDetail.value?.runtime_summary));
const planning = computed(() => selectedDetail.value?.planning || null);
const report = computed(() => selectedDetail.value?.report || null);
const executionNodes = computed(() => Array.isArray(selectedDetail.value?.execution_nodes) ? selectedDetail.value.execution_nodes : []);
const graphNodes = computed(() => executionNodes.value.filter((node) => String(node?.kind || "graph") !== "trigger"));
const eventRows = computed(() => Array.isArray(selectedDetail.value?.trace) ? selectedDetail.value.trace : []);
const triggerRules = computed(() => Array.isArray(planning.value?.trigger_rules) ? planning.value.trigger_rules : []);
const eventTypeOptions = computed(() => {
  return [...new Set(
    eventRows.value
      .map((item) => String(item?.event_type || item?.type || "").trim())
      .filter(Boolean)
  )].sort((a, b) => a.localeCompare(b));
});
const triggerRuleOptions = computed(() => {
  return [...new Set(
    triggerRules.value
      .map((item) => String(item?.rule_id || "").trim())
      .filter(Boolean)
  )].sort((a, b) => a.localeCompare(b));
});
const filteredEventRows = computed(() => {
  if (!selectedEventType.value) return eventRows.value;
  return eventRows.value.filter((item) => String(item?.event_type || item?.type || "").trim() === selectedEventType.value);
});
const filteredTriggerRules = computed(() => {
  if (!selectedTriggerRule.value) return triggerRules.value;
  return triggerRules.value.filter((item) => String(item?.rule_id || "").trim() === selectedTriggerRule.value);
});
const hasActiveFilters = computed(() => {
  return Boolean(selectedEventType.value || selectedTriggerRule.value);
});

const tabs = computed(() => [
  { id: "overview", label: "Overview", hint: recentV3Runs.value.length ? `${recentV3Runs.value.length} runs` : "" },
  { id: "graph", label: "Graph", hint: graphNodes.value.length ? `${graphNodes.value.length} nodes` : "" },
  { id: "events", label: "Events", hint: filteredEventRows.value.length ? `${filteredEventRows.value.length} items` : "" },
  { id: "triggers", label: "Triggers", hint: filteredTriggerRules.value.length ? `${filteredTriggerRules.value.length} rules` : "" },
  { id: "runtime", label: "Runtime Status", hint: runtimeSummary.value.run_mode?.label || "" },
]);

const lastUpdatedText = computed(() => {
  if (!lastUpdatedAt.value) return "—";
  return lastUpdatedAt.value.toLocaleTimeString("zh-CN");
});

const completedRunCount = computed(() => {
  return recentV3Runs.value.filter((run) => String(run.status || "").toLowerCase() === "completed").length;
});

const overviewCards = computed(() => [
  {
    label: "Recent V3 Runs",
    value: String(recentV3Runs.value.length),
    help: recentV3Runs.value.length ? `${completedRunCount.value} completed` : "暂无记录",
  },
  {
    label: "Graph Nodes",
    value: String(graphNodes.value.length),
    help: planning.value?.template_name ? `template: ${planning.value.template_name}` : "未选中 run",
  },
  {
    label: "Events",
    value: String(filteredEventRows.value.length),
    help: planning.value?.planning_mode === "llm" ? "当前规划已走模型" : "当前规划为规则模板",
  },
  {
    label: "Trigger Rules",
    value: String(filteredTriggerRules.value.length),
    help: triggerRules.value.length ? `${triggerRules.value.filter((rule) => isRuleEnabled(rule.rule_id)).length} enabled` : "无 trigger rules",
  },
]);
const runtimeStatusCards = computed(() => [
  {
    label: "Run Mode",
    value: runtimeSummary.value.run_mode?.label || "—",
    help: runtimeSummary.value.run_mode?.description || "",
  },
  {
    label: "Allowed",
    value: formatGovernanceCount(runtimeSummary.value.governance_summary.status_counts, "allowed"),
    help: "进入 follow-up 的次数",
  },
  {
    label: "Blocked",
    value: formatGovernanceCount(runtimeSummary.value.governance_summary.status_counts, "blocked"),
    help: "被治理规则拦截的次数",
  },
  {
    label: "Cooled Down",
    value: formatGovernanceCount(runtimeSummary.value.governance_summary.status_counts, "cooled_down"),
    help: "命中 cooldown 的次数",
  },
]);
const flowCards = computed(() => Array.isArray(runtimeSummary.value.flow_cards) ? runtimeSummary.value.flow_cards : []);
const governanceExplainItems = computed(() => {
  const summary = runtimeSummary.value.governance_summary;
  return Array.isArray(summary?.items) ? summary.items : [];
});
const demoScenarios = computed(() => Array.isArray(runtimeSummary.value.demo_scenarios) ? runtimeSummary.value.demo_scenarios : []);
const recentDemoRunsByScenario = computed(() => {
  const entries = Object.values(demoRunDetails.value || {}).filter(Boolean);
  return entries.reduce((acc, detail) => {
    const recoveryStatus = detail?.runtime_summary?.recovery_summary?.status;
    if (recoveryStatus === "recovered" && !acc.success) {
      acc.success = detail;
    }
    if (recoveryStatus === "recovery_failed" && !acc.no_code_changes) {
      acc.no_code_changes = detail;
    }
    return acc;
  }, { success: null, no_code_changes: null });
});
const demoCatalog = computed(() => [
  {
    id: "success",
    title: "Demo 1: 测试失败 -> 自动补救 -> 再测",
    goal: "让用户看到 event -> trigger -> follow-up 的完整主路径。",
    prompt: "在一个带失败测试的仓库里运行 `run tests`，然后观察 test_failed 如何触发 coding / tdd / test_runner。",
    watch: "Runtime Mode、Flow Cards、Recovered / Failed 节点收敛",
    actionLabel: "启动成功恢复 Demo",
    latestRunId: recentDemoRunsByScenario.value.success?.run?.run_id || "",
    latestStatusLabel: recentDemoRunsByScenario.value.success?.runtime_summary?.recovery_summary?.label || "Recovered",
  },
  {
    id: "no_code_changes",
    title: "Demo 2: 失败收敛 / 无代码变更",
    goal: "让用户看到 recovery 已触发，但会在 no-op patch 处受控收敛，而不是假装成功。",
    prompt: "运行 no_code_changes demo，观察 test_failed 之后虽然进入 tdd，但会明确停在 no_code_changes。",
    watch: "Recovery Failed、Flow Cards、stop reason、partial_completed",
    actionLabel: "启动失败收敛 Demo",
    latestRunId: recentDemoRunsByScenario.value.no_code_changes?.run?.run_id || "",
    latestStatusLabel: recentDemoRunsByScenario.value.no_code_changes?.runtime_summary?.recovery_summary?.label || "Recovery Failed",
  },
  {
    id: "replay_compare",
    title: "Demo 3: Replay Compare",
    goal: "让用户对照 recovery 主链的原始 run 和 replay 结果，确认它不是页面上的静态说明。",
    prompt: "对最近一次 recovery demo 执行 replay，直接比较 target skill、summary 和 replay success。",
    watch: "Replay Plan、Replay Result、source run / replay run 对照",
    actionLabel: "优先运行成功 Demo",
    latestRunId: recentDemoRunsByScenario.value.success?.run?.run_id || recentDemoRunsByScenario.value.no_code_changes?.run?.run_id || "",
    latestStatusLabel: replayCompareState.value.runId ? "Replay Ready" : "等待 demo run",
  },
]);
const recoveryStatusCards = computed(() => {
  const successRun = recentDemoRunsByScenario.value.success;
  const failureRun = recentDemoRunsByScenario.value.no_code_changes;
  return [
    {
      label: "Success Demo",
      value: successRun?.runtime_summary?.recovery_summary?.label || "Not Run",
      help: successRun?.run?.run_id ? shortChainId(successRun.run.run_id) : "还没有成功恢复 demo run",
    },
    {
      label: "Failure Demo",
      value: failureRun?.runtime_summary?.recovery_summary?.label || "Not Run",
      help: failureRun?.runtime_summary?.recovery_summary?.stop_reason || "还没有失败收敛 demo run",
    },
    {
      label: "Replay Compare",
      value: replayCompareState.value.runId ? (replayCompareState.value.replaySuccess ? "Replay Passed" : "Replay Failed") : "Not Run",
      help: replayCompareState.value.targetSkillName || "先运行一个 demo，再做 replay 对照",
    },
  ];
});

const overviewHighlights = computed(() => {
  const analyzeRepo = report.value?.shared_state?.analyze_repo || report.value?.node_outputs?.analyze_repo || {};
  return [
    planning.value?.goal_kind ? `goal: ${planning.value.goal_kind}` : null,
    planning.value?.repo_profile ? `profile: ${planning.value.repo_profile}` : null,
    Array.isArray(analyzeRepo.root_entries) && analyzeRepo.root_entries.length
      ? `${analyzeRepo.root_entries.length} root entries`
      : null,
    Array.isArray(planning.value?.execution_layers) && planning.value.execution_layers.length
      ? `${planning.value.execution_layers.length} execution layers`
      : null,
  ].filter(Boolean);
});

const selectedRunSummary = computed(() => {
  const meaningfulNodeSummary = graphNodes.value
    .map((node) => compactText(node?.summary || "", 180))
    .find((text) => text && text !== "—");
  if (meaningfulNodeSummary) return meaningfulNodeSummary;
  if (typeof planning.value?.template_reason === "string" && planning.value.template_reason.trim()) {
    return planning.value.template_reason.trim();
  }
  if (selectedRun.value?.task) {
    return `当前选中的是一次 ${planning.value?.goal_kind || "v3"} 运行：${selectedRun.value.task}`;
  }
  return "当前还没有可展示的运行摘要。";
});

const graphSections = computed(() => {
  if (!graphNodes.value.length) return [];
  const layers = Array.isArray(planning.value?.execution_layers) ? planning.value.execution_layers : [];
  const nodesById = new Map(graphNodes.value.map((node) => [node.node_id, node]));
  const usedNodeIds = new Set();
  const sections = layers
    .map((layer, index) => {
      const nodeIds = Array.isArray(layer) ? layer : [];
      const nodes = nodeIds.map((nodeId) => nodesById.get(nodeId)).filter(Boolean);
      nodes.forEach((node) => usedNodeIds.add(node.node_id));
      if (!nodes.length) return null;
      return {
        id: `layer-${index + 1}`,
        label: `Layer ${index + 1}`,
        description: nodeIds.join(" -> "),
        nodes,
      };
    })
    .filter(Boolean);
  const unlayered = graphNodes.value.filter((node) => !usedNodeIds.has(node.node_id));
  if (unlayered.length) {
    sections.push({
      id: "layer-unassigned",
      label: layers.length ? "Unassigned Graph Nodes" : "Graph Nodes",
      description: layers.length ? "这些节点没有被 execution_layers 收录。" : "当前按图节点顺序展示。",
      nodes: unlayered,
    });
  }
  return sections;
});

function normalizeV3Runs(items) {
  return (Array.isArray(items) ? items : []).filter((run) => String(run?.agent_version || "").toLowerCase() === "v3");
}

function statusLabel(status) {
  const value = String(status || "").toLowerCase();
  if (value === "completed") return "已完成";
  if (value === "failed") return "失败";
  if (value === "running") return "运行中";
  if (value === "partial_completed") return "部分完成";
  return status || "未知";
}

function statusClass(status) {
  const value = String(status || "").toLowerCase();
  if (value === "completed") return "badge-ok";
  if (value === "failed") return "badge-bad";
  if (value === "running") return "badge-warn";
  return "badge-muted";
}

function compactText(value, maxLength = 96) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return "—";
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
}

function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatRunOption(run) {
  return `${formatTime(run.updated_at)} · ${compactText(run.task, 44)}`;
}

function formatExecutionLayers(layers) {
  if (!Array.isArray(layers) || !layers.length) return "—";
  return layers
    .map((layer, index) => `L${index + 1}: ${(Array.isArray(layer) ? layer : []).join(" -> ")}`)
    .join(" | ");
}

function canInspectEventChain(item) {
  return Boolean(item && item.event_id && (item.execution_chain_id || item.event_type === "test_failed"));
}

function normalizedQueryValue(value) {
  return String(value || "").trim();
}

function replaceQueryState() {
  router.replace({
    name: "autonomy",
    query: {
      ...route.query,
      run_id: selectedRunId.value || undefined,
      tab: activeTab.value || undefined,
      event_type: selectedEventType.value || undefined,
      trigger_rule: selectedTriggerRule.value || undefined,
    },
  });
}

function summarizeV3Event(item) {
  const payload = item?.payload;
  if (payload && typeof payload === "object") {
    if (typeof payload.summary === "string" && payload.summary.trim()) return payload.summary.trim();
    if (typeof payload.message === "string" && payload.message.trim()) return payload.message.trim();
    if (typeof payload.node_id === "string" && payload.node_id) return `node=${payload.node_id}`;
    if (typeof payload.skill_name === "string" && payload.skill_name) return `skill=${payload.skill_name}`;
  }
  if (typeof item?.summary === "string" && item.summary.trim()) return item.summary.trim();
  return "—";
}

function shortChainId(value) {
  if (!value || typeof value !== "string") return "—";
  if (value.length <= 22) return value;
  return `${value.slice(0, 14)}…${value.slice(-6)}`;
}

function isRuleEnabled(ruleId) {
  const explicit = triggerStateOverrides.value[ruleId];
  if (typeof explicit === "boolean") return explicit;
  const rule = triggerRules.value.find((item) => item.rule_id === ruleId);
  return rule?.enabled !== false;
}

function triggerHitSummary(ruleId) {
  const item = triggerHitCounts.value.find((entry) => entry.rule_id === ruleId);
  if (!item) return "0 executed / 0 skipped";
  return `${Number(item.executed_count || 0)} executed / ${Number(item.skipped_count || 0)} skipped`;
}

async function loadRunDetail(runId) {
  const [detail, hitCounts, triggerStates] = await Promise.all([
    getRunDetail(runId),
    getV3TriggerHitCounts({ runId }),
    getV3TriggerRuleStates(),
  ]);
  selectedDetail.value = detail && typeof detail === "object" ? detail : null;
  triggerHitCounts.value = Array.isArray(hitCounts?.items) ? hitCounts.items : [];
  triggerStateOverrides.value = Object.fromEntries(
    (Array.isArray(triggerStates?.rules) ? triggerStates.rules : []).map((item) => [item.rule_id, Boolean(item.enabled)])
  );
}

async function loadDemoRunDetails(runs) {
  const candidates = (Array.isArray(runs) ? runs : [])
    .filter((run) => String(run?.task || "").trim() === "run tests and recover")
    .slice(0, 6);
  const details = await Promise.all(
    candidates.map(async (run) => {
      try {
        return await getRunDetail(run.run_id);
      } catch {
        return null;
      }
    })
  );
  demoRunDetails.value = Object.fromEntries(
    details
      .filter((item) => item?.run?.run_id)
      .map((item) => [item.run.run_id, item])
  );
}

async function loadAutonomy() {
  loading.value = true;
  error.value = "";
  try {
    const runs = await listRuns({ limit: 40, offset: 0 });
    recentV3Runs.value = normalizeV3Runs(runs?.runs);
    await loadDemoRunDetails(recentV3Runs.value);
    if (!recentV3Runs.value.length) {
      selectedRunId.value = "";
      selectedDetail.value = null;
      triggerHitCounts.value = [];
      triggerStateOverrides.value = {};
      return;
    }
    const currentExists = recentV3Runs.value.some((run) => run.run_id === selectedRunId.value);
    if (!selectedRunId.value || !currentExists) {
      selectedRunId.value = String(route.query.run_id || recentV3Runs.value[0].run_id);
    }
    if (selectedRunId.value) {
      await loadRunDetail(selectedRunId.value);
    }
    lastUpdatedAt.value = new Date();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载 autonomy runtime 失败";
  } finally {
    loading.value = false;
  }
}

async function launchRecoveryDemo(demo) {
  const scenario = demo?.id === "no_code_changes" ? "no_code_changes" : "success";
  demoLaunchingId.value = demo?.id || scenario;
  error.value = "";
  try {
    const result = await runV3RecoveryDemo(scenario);
    if (result?.run_id) {
      await loadAutonomy();
      selectedRunId.value = result.run_id;
      activeTab.value = "overview";
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "启动 recovery demo 失败";
  } finally {
    demoLaunchingId.value = "";
  }
}

function openDemoRun(demo) {
  if (!demo?.latestRunId) return;
  router.push({
    name: "execution",
    params: { runId: demo.latestRunId },
    query: { version: "v3" },
  });
}

async function openReplayCompare(demo) {
  const runId = demo?.latestRunId;
  if (!runId) return;
  replayCompareLoading.value = true;
  replayCompareDemoId.value = demo.id || "";
  replayCompareError.value = "";
  try {
    const [plan, detail] = await Promise.all([
      getV3RunReplayPlan(runId),
      demoRunDetails.value[runId] ? Promise.resolve(demoRunDetails.value[runId]) : getRunDetail(runId),
    ]);
    const firstTarget = Array.isArray(plan?.available_targets) ? plan.available_targets[0] : null;
    if (!firstTarget?.event_id) {
      throw new Error("当前 demo run 没有可 replay 的 recovery target。");
    }
    const replayResult = await replayV3EventChain(runId, { eventId: firstTarget.event_id });
    replayCompareState.value = {
      runId,
      demoTitle: demo.title || "",
      targetSkillName: replayResult?.metadata?.target_skill_name || firstTarget.target_skill_name || "",
      summary: replayResult?.summary || "",
      originalSummary: detail?.runtime_summary?.recovery_summary?.label
        ? `原始 recovery：${detail.runtime_summary.recovery_summary.label} · ${detail.runtime_summary.recovery_summary.patch_summary || detail.runtime_summary.recovery_summary.stop_reason || "无额外摘要"}`
        : "原始 run 未记录 recovery summary。",
      replaySuccess: Boolean(replayResult?.success),
    };
  } catch (err) {
    replayCompareState.value = {
      runId: "",
      demoTitle: "",
      targetSkillName: "",
      summary: "",
      originalSummary: "",
      replaySuccess: false,
    };
    replayCompareError.value = err instanceof Error ? err.message : "读取 replay compare 失败";
  } finally {
    replayCompareLoading.value = false;
    replayCompareDemoId.value = "";
  }
}

async function inspectEventChain(item) {
  if (!selectedRunId.value) return;
  if (!canInspectEventChain(item)) {
    selectedEventId.value = item?.event_id || "";
    eventChain.value = null;
    eventChainView.value = "";
    eventError.value = "这条事件没有可展开的 event chain。请选择带 execution_chain_id 的事件，或 test_failed 根事件。";
    return;
  }
  eventLoading.value = true;
  eventError.value = "";
  selectedEventId.value = item.event_id;
  selectedEventType.value = String(item.event_type || item.type || "").trim();
  try {
    const [chain, view] = await Promise.all([
      getV3EventChain(selectedRunId.value, { eventId: item.event_id }),
      getV3EventChainView(selectedRunId.value, { eventId: item.event_id }),
    ]);
    eventChain.value = chain;
    eventChainView.value = view;
  } catch (err) {
    eventChain.value = null;
    eventChainView.value = "";
    eventError.value = err instanceof Error ? err.message : "读取事件链失败";
  } finally {
    eventLoading.value = false;
  }
}

async function toggleRule(ruleId) {
  if (!ruleId) return;
  togglingRuleId.value = ruleId;
  try {
    await setV3TriggerRuleEnabled(ruleId, !isRuleEnabled(ruleId));
    const states = await getV3TriggerRuleStates();
    triggerStateOverrides.value = Object.fromEntries(
      (Array.isArray(states?.rules) ? states.rules : []).map((item) => [item.rule_id, Boolean(item.enabled)])
    );
  } catch (err) {
    error.value = err instanceof Error ? err.message : "更新 trigger rule 状态失败";
  } finally {
    togglingRuleId.value = "";
  }
}

function clearFilters() {
  selectedEventType.value = "";
  selectedTriggerRule.value = "";
}

watch(
  () => selectedRunId.value,
  async (runId, previous) => {
    if (!runId || runId === previous) return;
    replaceQueryState();
    try {
      await loadRunDetail(runId);
      eventChain.value = null;
      eventChainView.value = "";
      eventError.value = "";
      selectedEventId.value = "";
    } catch (err) {
      error.value = err instanceof Error ? err.message : "切换 run 失败";
    }
  }
);

watch(
  () => [activeTab.value, selectedEventType.value, selectedTriggerRule.value],
  () => {
    replaceQueryState();
  }
);

watch(
  () => route.query,
  (query) => {
    const nextRunId = normalizedQueryValue(query.run_id);
    const nextTab = normalizedQueryValue(query.tab) || "overview";
    const nextEventType = normalizedQueryValue(query.event_type);
    const nextTriggerRule = normalizedQueryValue(query.trigger_rule);
    if (nextRunId !== selectedRunId.value && nextRunId) {
      selectedRunId.value = nextRunId;
    }
    if (nextTab !== activeTab.value) {
      activeTab.value = nextTab;
    }
    if (nextEventType !== selectedEventType.value) {
      selectedEventType.value = nextEventType;
    }
    if (nextTriggerRule !== selectedTriggerRule.value) {
      selectedTriggerRule.value = nextTriggerRule;
    }
  }
);

onMounted(loadAutonomy);
</script>

<style scoped>
.autonomy-hero {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: flex-start;
}

.autonomy-lead {
  max-width: 760px;
}

.autonomy-hero-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.autonomy-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-end;
}

.autonomy-filter-panel {
  padding-top: 18px;
}

.autonomy-toolbar-main,
.autonomy-toolbar-side,
.autonomy-toolbar-links,
.autonomy-run-meta,
.autonomy-highlight-list,
.autonomy-chain-meta,
.autonomy-active-filters {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.autonomy-filter-grid {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(220px, 1fr) auto;
  gap: 16px;
  align-items: end;
}

.autonomy-filter-actions {
  display: flex;
  justify-content: flex-end;
}

.autonomy-active-filters {
  margin-top: 14px;
}

.autonomy-field {
  display: grid;
  gap: 8px;
  min-width: min(420px, 100%);
}

.autonomy-field span {
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.autonomy-field select {
  width: 100%;
}

.autonomy-stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.autonomy-stat-card {
  margin-bottom: 0;
  background:
    radial-gradient(circle at 100% 0%, rgba(13, 148, 136, 0.14), transparent 36%),
    #fff;
}

.autonomy-stat-card span,
.autonomy-stat-card small {
  display: block;
  color: var(--text-muted);
}

.autonomy-stat-card span {
  font-size: 0.76rem;
  font-weight: 800;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.autonomy-stat-card strong {
  display: block;
  margin-top: 8px;
  font-family: var(--font-mono);
  font-size: 1.7rem;
  letter-spacing: -0.04em;
}

.autonomy-run-head,
.autonomy-section-head,
.autonomy-events-panel-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.autonomy-run-head h3,
.autonomy-section-head h3,
.autonomy-events-panel-head h4,
.autonomy-overview-answer h4,
.autonomy-overview-list h4 {
  margin: 0 0 6px;
}

.autonomy-tabs {
  margin-bottom: 20px;
}

.autonomy-overview-layout,
.autonomy-events-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
  gap: 16px;
}

.autonomy-overview-answer,
.autonomy-overview-list,
.autonomy-events-list,
.autonomy-events-panel {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: #fbfcfe;
  padding: 16px;
}

.autonomy-summary {
  margin: 0 0 12px;
  font-size: 0.98rem;
  line-height: 1.7;
  color: var(--text-primary);
}

.is-selected-row {
  background: rgba(79, 70, 229, 0.06);
}

.autonomy-panel-note {
  margin-top: 12px;
}

.autonomy-graph-sections {
  margin-top: 18px;
}

.autonomy-node-summary {
  margin: 0;
  color: var(--text-primary);
  line-height: 1.65;
}

.autonomy-events-list {
  display: grid;
  gap: 10px;
  align-content: start;
  max-height: 720px;
  overflow: auto;
}

.autonomy-event-row {
  width: 100%;
  text-align: left;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: #fff;
  padding: 12px 14px;
}

.autonomy-event-row:hover {
  border-color: rgba(79, 70, 229, 0.24);
  background: #f8f9ff;
}

.autonomy-event-row:disabled {
  opacity: 1;
  cursor: not-allowed;
}

.autonomy-event-row.is-selected {
  border-color: rgba(79, 70, 229, 0.3);
  box-shadow: inset 0 0 0 1px rgba(79, 70, 229, 0.18);
  background: rgba(79, 70, 229, 0.05);
}

.autonomy-event-row.is-disabled {
  background: #f8fafc;
  border-style: dashed;
}

.autonomy-event-row.is-disabled:hover {
  border-color: var(--border-subtle);
  background: #f8fafc;
}

.autonomy-event-row-head,
.autonomy-event-row-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.autonomy-event-row-meta {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 0.84rem;
}

.autonomy-event-row-foot {
  margin-top: 10px;
  display: flex;
  justify-content: flex-start;
}

.autonomy-chain-view {
  margin-top: 12px;
  max-height: 520px;
}

.autonomy-inline-note {
  margin: 6px 0 0;
}

.autonomy-status-badge.badge-ok {
  background: rgba(13, 148, 136, 0.15);
  color: #0f766e;
  border-color: rgba(13, 148, 136, 0.28);
}

.autonomy-status-badge.badge-bad {
  background: rgba(220, 38, 38, 0.12);
  color: #b91c1c;
  border-color: rgba(220, 38, 38, 0.22);
}

.autonomy-status-badge.badge-warn {
  background: rgba(245, 158, 11, 0.16);
  color: #b45309;
  border-color: rgba(245, 158, 11, 0.25);
}

.autonomy-status-badge.badge-muted {
  background: #eef2f7;
  color: #475569;
  border-color: rgba(100, 116, 139, 0.18);
}

.badge-enabled {
  background: rgba(13, 148, 136, 0.12);
  color: #0f766e;
  border-color: rgba(13, 148, 136, 0.22);
}

.badge-disabled {
  background: rgba(100, 116, 139, 0.12);
  color: #475569;
  border-color: rgba(100, 116, 139, 0.18);
}

@media (max-width: 980px) {
  .autonomy-hero,
  .autonomy-toolbar,
  .autonomy-run-head,
  .autonomy-section-head,
  .autonomy-events-panel-head {
    flex-direction: column;
  }

  .autonomy-stat-grid,
  .autonomy-filter-grid,
  .autonomy-overview-layout,
  .autonomy-events-layout {
    grid-template-columns: 1fr;
  }

  .autonomy-field {
    min-width: 0;
  }
}
</style>
