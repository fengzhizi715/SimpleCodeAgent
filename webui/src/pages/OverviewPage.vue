<template>
  <section class="panel overview-panel">
    <div class="overview-head">
      <div>
        <h2>系统概况</h2>
        <p class="muted overview-lead">
          本仓库演示<strong>单 Agent（V1）</strong>与<strong>多 Agent 编排（V2）</strong>的工程化路径；WebUI 当前以运行、观测与 RAG 管理为主。
        </p>
      </div>
      <div class="overview-head-actions">
        <button class="btn-secondary btn-sm" :disabled="overviewLoading || statsLoading || agentsLoading" @click="loadOverview">
          {{ overviewLoading || statsLoading || agentsLoading ? "刷新中…" : "刷新概况" }}
        </button>
        <span class="muted overview-updated">最近刷新：{{ lastUpdatedText }}</span>
      </div>
    </div>
    <div class="overview-grid">
      <div class="overview-card">
        <h3>后端服务</h3>
        <p v-if="overviewLoading" class="muted">检测中…</p>
        <template v-else>
          <p class="overview-status">
            <span class="status-dot" :class="apiOk ? 'is-ok' : 'is-down'" />
            <strong>{{ apiOk ? "API 已连接" : "API 未连接" }}</strong>
          </p>
          <p v-if="apiOk && health" class="muted overview-meta">
            {{ health.app_name }} · {{ health.env }}
          </p>
          <div v-if="apiOk && health" class="overview-kv">
            <p><span>LLM_BASE_URL</span><code>{{ health.llm_base_url || "—" }}</code></p>
            <p><span>LLM_MODEL</span><code>{{ health.llm_model || "—" }}</code></p>
          </div>
          <div v-if="apiOk" class="overview-llm-form">
            <label>LLM_BASE_URL</label>
            <input v-model="llmForm.llm_base_url" placeholder="https://api.openai.com/v1" />
            <label>LLM_MODEL</label>
            <input v-model="llmForm.llm_model" placeholder="gpt-4.1-mini" />
            <div class="row overview-llm-actions">
              <div class="overview-llm-buttons">
                <button class="btn-secondary btn-sm" :disabled="savingLLM" @click="saveLLMSettings">
                  {{ savingLLM ? "保存中…" : "保存 LLM 配置" }}
                </button>
                <button
                  class="btn-secondary btn-sm"
                  :disabled="validatingLLM || savingLLM"
                  @click="validateCurrentLLMSettings"
                >
                  {{ validatingLLM ? "校验中…" : "校验 LLM 连通性" }}
                </button>
              </div>
              <span v-if="llmValidateMessage" class="muted overview-llm-message">{{ llmValidateMessage }}</span>
              <span v-if="llmError" class="error overview-llm-message">{{ llmError }}</span>
            </div>
          </div>
          <p v-else class="muted overview-meta">请在本机 <code>8000</code> 端口启动 FastAPI 后刷新本页。</p>
        </template>
      </div>
      <div class="overview-card">
        <h3>主要能力</h3>
        <ul class="overview-list">
          <li><strong>运行任务</strong>：提交目标，多 Agent 协作执行并落库</li>
          <li><strong>历史记录</strong>：按版本查看运行摘要与回放</li>
          <li><strong>RAG</strong>：Chroma 向量库、文档导入与索引维护</li>
        </ul>
      </div>
      <div class="overview-card">
        <h3>数据概览</h3>
        <p v-if="statsLoading" class="muted">加载中…</p>
        <template v-else>
          <p class="overview-stat">
            <span class="overview-stat-label">V2 历史（含 workspace）</span>
            <span class="overview-stat-value">{{ historyTotal !== null ? `${historyTotal} 条` : "—" }}</span>
          </p>
          <p class="muted overview-hint">
            <RouterLink to="/run">新建运行</RouterLink>
            ·
            <RouterLink to="/history">查看历史</RouterLink>
            ·
            <RouterLink to="/rag">管理 RAG</RouterLink>
          </p>
        </template>
      </div>
      <div class="overview-card">
        <h3>当前智能体</h3>
        <p v-if="agentsLoading" class="muted">加载中…</p>
        <template v-else>
          <p class="overview-stat">
            <span class="overview-stat-label">已注册智能体</span>
            <span class="overview-stat-value">{{ agentsTotal !== null ? `${agentsTotal} 个` : "—" }}</span>
          </p>
          <div v-if="agentNames.length" class="overview-agent-chips">
            <span v-for="name in agentNames" :key="name" class="overview-agent-chip">{{ name }}</span>
          </div>
          <p v-else class="muted overview-meta">
            暂未获取到智能体列表。
          </p>
          <p class="muted overview-hint">
            <RouterLink to="/agents">查看全部</RouterLink>
          </p>
        </template>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { getHealthz, listAgents, listV2Runs, updateLLMSettings, validateLLMSettings } from "../api";

const overviewLoading = ref(true);
const statsLoading = ref(true);
const apiOk = ref(false);
const health = ref(null);
const historyTotal = ref(null);
const agentsLoading = ref(true);
const agentsTotal = ref(null);
const agentNames = ref([]);
const lastUpdatedAt = ref(null);
const savingLLM = ref(false);
const validatingLLM = ref(false);
const llmError = ref("");
const llmValidateMessage = ref("");
const llmForm = ref({
  llm_base_url: "",
  llm_model: "",
});

const lastUpdatedText = computed(() => {
  if (!lastUpdatedAt.value) return "—";
  return lastUpdatedAt.value.toLocaleTimeString();
});

async function loadOverview() {
  overviewLoading.value = true;
  statsLoading.value = true;
  try {
    try {
      const h = await getHealthz();
      health.value = h;
      llmForm.value = {
        llm_base_url: h?.llm_base_url || "",
        llm_model: h?.llm_model || "",
      };
      apiOk.value = true;
    } catch {
      health.value = null;
      apiOk.value = false;
    }
  } finally {
    overviewLoading.value = false;
  }

  try {
    const data = await listV2Runs({ limit: 1, offset: 0 });
    historyTotal.value = typeof data.total === "number" ? data.total : null;
  } catch {
    historyTotal.value = null;
  } finally {
    statsLoading.value = false;
  }

  try {
    const data = await listAgents();
    const agents = Array.isArray(data.agents) ? data.agents : [];
    agentsTotal.value = typeof data.total === "number" ? data.total : agents.length;
    agentNames.value = agents.map((item) => item.agent_id).filter(Boolean);
  } catch {
    agentsTotal.value = null;
    agentNames.value = [];
  } finally {
    agentsLoading.value = false;
  }
  lastUpdatedAt.value = new Date();
}

async function saveLLMSettings() {
  llmError.value = "";
  llmValidateMessage.value = "";
  const llmBaseUrl = llmForm.value.llm_base_url.trim();
  const llmModel = llmForm.value.llm_model.trim();
  if (!llmBaseUrl || !llmModel) {
    llmError.value = "LLM_BASE_URL 和 LLM_MODEL 不能为空。";
    return;
  }
  savingLLM.value = true;
  try {
    const h = await updateLLMSettings({
      llm_base_url: llmBaseUrl,
      llm_model: llmModel,
    });
    health.value = h;
    llmForm.value = {
      llm_base_url: h?.llm_base_url || "",
      llm_model: h?.llm_model || "",
    };
    apiOk.value = true;
    lastUpdatedAt.value = new Date();
  } catch (err) {
    llmError.value = err instanceof Error ? err.message : "保存失败";
  } finally {
    savingLLM.value = false;
  }
}

async function validateCurrentLLMSettings() {
  llmError.value = "";
  llmValidateMessage.value = "";
  validatingLLM.value = true;
  try {
    const result = await validateLLMSettings();
    llmValidateMessage.value = `校验通过（${result.latency_ms} ms）`;
    apiOk.value = true;
    lastUpdatedAt.value = new Date();
  } catch (err) {
    llmError.value = err instanceof Error ? err.message : "校验失败";
  } finally {
    validatingLLM.value = false;
  }
}

onMounted(loadOverview);
</script>

<style scoped>
.overview-panel h2 {
  margin-bottom: 6px;
}

.overview-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.overview-head-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}

.overview-updated {
  font-size: 0.75rem;
}

.overview-lead {
  margin-bottom: 0;
}

.overview-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

@media (max-width: 900px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }
}

.overview-card {
  background: linear-gradient(180deg, #fafbfe 0%, #f4f6fb 100%);
  border: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
  border-radius: var(--radius-sm, 8px);
  padding: 16px 18px;
}

.overview-card h3 {
  margin: 0 0 12px;
  font-size: 0.9375rem;
  font-weight: 700;
  color: var(--text-primary, #1a1d26);
}

.overview-status {
  margin: 0 0 6px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.is-ok {
  background: #10b981;
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.25);
}

.status-dot.is-down {
  background: #f59e0b;
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.25);
}

.overview-meta {
  margin: 0;
  font-size: 0.8125rem;
}

.overview-kv p {
  margin: 0 0 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 0.78rem;
}

.overview-kv span {
  color: var(--text-muted, #8b929e);
}

.overview-llm-form {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--border-subtle, rgba(15, 20, 25, 0.08));
}

.overview-llm-form label {
  margin-top: 6px;
}

.overview-llm-actions {
  margin-top: 14px;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}

.overview-llm-buttons {
  display: inline-flex;
  gap: 8px;
  flex-wrap: nowrap;
}

.overview-llm-message {
  line-height: 1.3;
}

.overview-list {
  margin: 0;
  padding-left: 1.15rem;
  font-size: 0.875rem;
  color: var(--text-secondary, #5c6370);
  line-height: 1.55;
}

.overview-list li + li {
  margin-top: 8px;
}

.overview-stat {
  margin: 0 0 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.overview-stat-label {
  font-size: 0.8125rem;
  color: var(--text-muted, #8b929e);
}

.overview-stat-value {
  font-size: 1.125rem;
  font-weight: 700;
  color: var(--text-primary, #1a1d26);
}

.overview-hint {
  margin: 0;
  font-size: 0.8125rem;
}

.overview-agent-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.overview-agent-chip {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--accent-text, #4338ca);
  background: var(--accent-soft, rgba(79, 70, 229, 0.12));
  border: 1px solid rgba(79, 70, 229, 0.24);
}

@media (max-width: 900px) {
  .overview-head {
    flex-direction: column;
  }
  .overview-head-actions {
    align-items: flex-start;
  }
}
</style>
