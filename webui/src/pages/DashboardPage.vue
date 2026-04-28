<template>
  <section class="panel dashboard-hero">
    <div>
      <h2>Token Dashboard</h2>
      <p class="muted">
        统计所有顶层运行的 token 消耗。旧历史若未记录 usage，会以 0 计入。
      </p>
    </div>
    <button class="btn-secondary btn-sm" :disabled="loading" @click="loadDashboard">
      {{ loading ? "刷新中..." : "刷新统计" }}
    </button>
  </section>

  <p v-if="error" class="error">{{ error }}</p>

  <section class="dashboard-stat-grid">
    <article class="panel dashboard-stat-card">
      <span>Total Tokens</span>
      <strong>{{ formatNumber(totals.total_tokens) }}</strong>
      <small>{{ formatNumber(totals.run_count) }} runs</small>
    </article>
    <article class="panel dashboard-stat-card">
      <span>Prompt Tokens</span>
      <strong>{{ formatNumber(totals.prompt_tokens) }}</strong>
      <small>输入上下文消耗</small>
    </article>
    <article class="panel dashboard-stat-card">
      <span>Completion Tokens</span>
      <strong>{{ formatNumber(totals.completion_tokens) }}</strong>
      <small>模型输出消耗</small>
    </article>
  </section>

  <section class="grid-two">
    <div class="panel">
      <h3>按版本统计</h3>
      <table v-if="byVersion.length">
        <thead>
          <tr>
            <th>版本</th>
            <th>运行数</th>
            <th>Total</th>
            <th>Prompt</th>
            <th>Completion</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in byVersion" :key="item.agent_version">
            <td><span class="agent-version" :class="`agent-version--${item.agent_version}`">{{ item.agent_version }}</span></td>
            <td>{{ formatNumber(item.run_count) }}</td>
            <td>{{ formatNumber(item.total_tokens) }}</td>
            <td>{{ formatNumber(item.prompt_tokens) }}</td>
            <td>{{ formatNumber(item.completion_tokens) }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">暂无版本统计。</p>
    </div>

    <div class="panel">
      <h3>按模型统计</h3>
      <table v-if="byModel.length">
        <thead>
          <tr>
            <th>模型</th>
            <th>运行数</th>
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in byModel" :key="item.model">
            <td class="mono">{{ item.model || "—" }}</td>
            <td>{{ formatNumber(item.run_count) }}</td>
            <td>{{ formatNumber(item.total_tokens) }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">暂无模型统计。</p>
    </div>
  </section>

  <section class="panel">
    <h3>最近 14 天趋势</h3>
    <div v-if="byDay.length" class="usage-bars">
      <div v-for="item in byDay" :key="item.day" class="usage-bar-row">
        <span>{{ item.day }}</span>
        <div class="usage-bar-track">
          <div class="usage-bar-fill" :style="{ width: barWidth(item.total_tokens) }" />
        </div>
        <strong>{{ formatNumber(item.total_tokens) }}</strong>
      </div>
    </div>
    <p v-else class="muted">暂无按日期统计。</p>
  </section>

  <section class="panel">
    <h3>Token 消耗 Top Runs</h3>
    <table v-if="recentRuns.length">
      <thead>
        <tr>
          <th>版本</th>
          <th>任务</th>
          <th>模型</th>
          <th>Total</th>
          <th>Prompt</th>
          <th>Completion</th>
          <th>更新时间</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="run in recentRuns" :key="run.run_id">
          <td><span class="agent-version" :class="`agent-version--${run.agent_version}`">{{ run.agent_version }}</span></td>
          <td>
            <RouterLink :to="{ name: 'trace', params: { runId: run.run_id }, query: { version: run.agent_version } }">
              {{ clip(run.task) }}
            </RouterLink>
          </td>
          <td class="mono">{{ run.model || "—" }}</td>
          <td>{{ formatNumber(run.total_tokens) }}</td>
          <td>{{ formatNumber(run.prompt_tokens) }}</td>
          <td>{{ formatNumber(run.completion_tokens) }}</td>
          <td>{{ formatTime(run.updated_at) }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">暂无运行 token 数据。</p>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { getUsageSummary } from "../api";

const loading = ref(false);
const error = ref("");
const summary = ref({
  totals: {},
  by_version: [],
  by_model: [],
  by_day: [],
  recent_runs: [],
});

const totals = computed(() => summary.value.totals || {});
const byVersion = computed(() => asArray(summary.value.by_version));
const byModel = computed(() => asArray(summary.value.by_model));
const byDay = computed(() => asArray(summary.value.by_day).slice().reverse());
const recentRuns = computed(() => asArray(summary.value.recent_runs));
const maxDailyTokens = computed(() => Math.max(...byDay.value.map((item) => Number(item.total_tokens || 0)), 1));

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("zh-CN");
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
  });
}

function clip(value, maxLength = 52) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text || "—";
}

function barWidth(value) {
  const percent = Math.max(4, Math.round((Number(value || 0) / maxDailyTokens.value) * 100));
  return `${percent}%`;
}

async function loadDashboard() {
  loading.value = true;
  error.value = "";
  try {
    const data = await getUsageSummary({ recentLimit: 20 });
    summary.value = data && typeof data === "object" ? data : summary.value;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载 token 统计失败";
  } finally {
    loading.value = false;
  }
}

onMounted(loadDashboard);
</script>

<style scoped>
.dashboard-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.dashboard-hero p {
  margin-bottom: 0;
}

.dashboard-stat-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.dashboard-stat-card {
  margin-bottom: 20px;
  background:
    radial-gradient(circle at 100% 0%, rgba(14, 116, 144, 0.16), transparent 34%),
    #fff;
}

.dashboard-stat-card span,
.dashboard-stat-card small {
  display: block;
  color: var(--text-muted);
}

.dashboard-stat-card span {
  font-size: 0.76rem;
  font-weight: 800;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.dashboard-stat-card strong {
  display: block;
  margin-top: 8px;
  font-family: var(--font-mono);
  font-size: 1.8rem;
  letter-spacing: -0.04em;
}

.dashboard-stat-card small {
  margin-top: 4px;
}

.mono {
  font-family: var(--font-mono);
  font-size: 0.8125rem;
}

.usage-bars {
  display: grid;
  gap: 10px;
}

.usage-bar-row {
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr) 100px;
  gap: 12px;
  align-items: center;
}

.usage-bar-row span,
.usage-bar-row strong {
  font-family: var(--font-mono);
  font-size: 0.8125rem;
}

.usage-bar-row strong {
  text-align: right;
}

.usage-bar-track {
  height: 12px;
  overflow: hidden;
  border-radius: 999px;
  background: #e2e8f0;
}

.usage-bar-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #1d4ed8, #0f766e);
}

@media (max-width: 900px) {
  .dashboard-stat-grid {
    grid-template-columns: 1fr;
  }

  .dashboard-hero {
    flex-direction: column;
  }

  .usage-bar-row {
    grid-template-columns: 1fr;
    gap: 5px;
  }

  .usage-bar-row strong {
    text-align: left;
  }
}
</style>
