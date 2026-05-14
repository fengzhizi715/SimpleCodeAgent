<template>
  <section class="panel">
    <h2>智能体列表</h2>
    <p class="muted">展示当前运行时注册的 v2 agents；点击 Reviewer 可配置 review 策略。</p>

    <div class="row agents-toolbar">
      <span class="badge">总数：{{ totalLabel }}</span>
    </div>

    <p v-if="errorMsg" class="error">{{ errorMsg }}</p>

    <p v-if="!loading && !agents.length" class="muted">暂无 v2 agent 数据。</p>

    <div v-else class="agents-grid">
      <article
        v-for="agent in agents"
        :key="agent.agent_id"
        class="agent-card"
        :class="{ 'is-selected': selectedAgentId === agent.agent_id, 'is-configurable': agent.agent_id === 'reviewer' }"
        @click="selectAgent(agent.agent_id)"
      >
        <header class="agent-card-head">
          <code class="agent-id">{{ agent.agent_id }}</code>
          <span class="badge">{{ agent.availability || "unknown" }}</span>
        </header>
        <p class="agent-role">{{ agent.role || "—" }}</p>
        <p class="agent-desc">{{ agent.description || "—" }}</p>
        <div class="agent-caps">
          <strong>能力</strong>
          <p v-if="agent.capabilities?.length" class="muted">{{ agent.capabilities.join(" / ") }}</p>
          <p v-else class="muted">—</p>
        </div>
      </article>
    </div>
  </section>

  <section v-if="selectedAgentId === 'reviewer'" class="panel reviewer-settings-panel">
    <div class="v2-agent-config-head">
      <div>
        <h3>Reviewer 策略配置</h3>
        <p class="muted">
          这里保存的是 WebUI 级默认策略。新建 V2 运行并启用 Reviewer 时，会自动带上这份配置。
        </p>
      </div>
      <button type="button" class="btn-secondary btn-sm" @click="resetReviewerSettings">恢复默认</button>
    </div>

    <div class="grid-two">
      <div>
        <label>严格度</label>
        <select v-model="reviewStrategy.strictness">
          <option value="light">light（轻量提示）</option>
          <option value="normal">normal（推荐）</option>
          <option value="strict">strict（严格阻断）</option>
        </select>
      </div>
      <div>
        <label>测试失败联动</label>
        <select v-model="reviewStrategy.test_failure_mode">
          <option value="block">block：测试失败作为高风险</option>
          <option value="suggest">suggest：测试失败作为建议</option>
          <option value="off">off：不联动测试结果</option>
        </select>
      </div>
      <label class="inline-toggle">
        <input type="checkbox" v-model="reviewStrategy.llm_enabled" />
        <span>启用 LLM Review</span>
      </label>
      <div>
        <label>Max Issues</label>
        <input v-model.number="reviewStrategy.max_issues" type="number" min="1" max="10" />
      </div>
    </div>

    <div style="margin-top: 12px">
      <label>规则分组</label>
      <div class="review-rule-grid">
        <label v-for="group in reviewRuleGroups" :key="group.id" class="review-rule-option">
          <input
            type="checkbox"
            :checked="reviewStrategy.rule_groups.includes(group.id)"
            @change="toggleReviewRuleGroup(group.id)"
          />
          <span>
            <strong>{{ group.label }}</strong>
            <small>{{ group.help }}</small>
          </span>
        </label>
      </div>
    </div>

    <div style="margin-top: 12px">
      <label>LLM 关注点（可选，逗号分隔）</label>
      <input v-model="reviewFocusAreasText" placeholder="例如 security, tests, v1-boundary" />
    </div>

    <div class="reviewer-actions">
      <div class="reviewer-save-actions">
        <button type="button" class="btn-primary" @click="saveReviewerSettings">保存 Reviewer 配置</button>
        <span v-if="saveMessage" class="muted">{{ saveMessage }}</span>
      </div>
      <RouterLink class="reviewer-run-cta" to="/run">
        <span>
          <strong>去新建运行</strong>
          <small>启用 V2 Reviewer 后会自动使用当前策略</small>
        </span>
        <span class="reviewer-run-arrow">→</span>
      </RouterLink>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { listAgents } from "../api";
import {
  defaultReviewRuleGroups,
  loadReviewStrategy,
  resetReviewStrategy,
  reviewRuleGroups,
  saveReviewStrategy,
} from "../reviewerConfig";

const loading = ref(false);
const errorMsg = ref("");
const agents = ref([]);
const route = useRoute();
const router = useRouter();
const selectedAgentId = ref("");
const saveMessage = ref("");
const reviewStrategy = reactive(loadReviewStrategy());
const reviewFocusAreasText = ref(reviewStrategy.focus_areas.join(", "));

const totalLabel = computed(() => `${agents.value.length} 个`);

function assignReviewStrategy(next) {
  Object.assign(reviewStrategy, next);
  reviewFocusAreasText.value = reviewStrategy.focus_areas.join(", ");
}

async function loadAgents() {
  loading.value = true;
  errorMsg.value = "";
  try {
    const data = await listAgents();
    agents.value = Array.isArray(data.v2_agents)
      ? data.v2_agents
      : Array.isArray(data.agents)
        ? data.agents
        : [];
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    errorMsg.value = message || "加载智能体列表失败。";
    agents.value = [];
  } finally {
    loading.value = false;
  }
}

function selectAgent(agentId) {
  selectedAgentId.value = agentId === "reviewer" ? "reviewer" : agentId;
  if (agentId === "reviewer") {
    router.replace({ path: "/agents", query: { agent: "reviewer" } });
    return;
  }
  router.replace({ path: "/agents" });
}

function toggleReviewRuleGroup(groupId) {
  const selected = new Set(reviewStrategy.rule_groups);
  if (selected.has(groupId)) {
    selected.delete(groupId);
  } else {
    selected.add(groupId);
  }
  reviewStrategy.rule_groups = defaultReviewRuleGroups.filter((id) => selected.has(id));
}

function saveReviewerSettings() {
  const saved = saveReviewStrategy({
    ...reviewStrategy,
    focus_areas: reviewFocusAreasText.value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean)
      .slice(0, 8),
  });
  assignReviewStrategy(saved);
  saveMessage.value = "已保存，下一次 V2 Reviewer 运行会使用这份配置。";
}

function resetReviewerSettings() {
  assignReviewStrategy(resetReviewStrategy());
  saveMessage.value = "已恢复默认配置。";
}

onMounted(() => {
  loadAgents();
  if (route.query.agent === "reviewer") {
    selectedAgentId.value = "reviewer";
  }
});
</script>

<style scoped>
.agents-toolbar {
  margin: 12px 0 14px;
}

.agents-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

@media (max-width: 900px) {
  .agents-grid {
    grid-template-columns: 1fr;
  }
}

.agent-card {
  border: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
  border-radius: var(--radius-sm, 8px);
  background: linear-gradient(180deg, #fafbfe 0%, #f4f6fb 100%);
  padding: 12px 14px;
  cursor: default;
  transition:
    border-color 0.16s ease,
    box-shadow 0.16s ease,
    transform 0.16s ease;
}

.agent-card.is-configurable {
  cursor: pointer;
}

.agent-card.is-configurable:hover,
.agent-card.is-selected {
  border-color: var(--accent, #4f46e5);
  box-shadow: 0 8px 26px rgba(79, 70, 229, 0.12);
  transform: translateY(-1px);
}

.agent-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.agent-id {
  font-size: 0.8125rem;
}

.agent-role {
  margin: 8px 0 4px;
  font-weight: 700;
  color: var(--text-primary, #1a1d26);
}

.agent-desc {
  margin: 0;
  color: var(--text-secondary, #5c6370);
  font-size: 0.875rem;
}

.agent-caps {
  margin-top: 8px;
  font-size: 0.8125rem;
}

.agent-caps strong {
  display: inline-block;
  margin-bottom: 2px;
}

.reviewer-settings-panel {
  border-color: rgba(79, 70, 229, 0.18);
}

.reviewer-actions {
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 16px;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
}

.reviewer-save-actions {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.reviewer-run-cta {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  min-width: 250px;
  padding: 12px 14px 12px 16px;
  border: 1px solid rgba(14, 116, 144, 0.26);
  border-radius: 16px;
  background:
    linear-gradient(135deg, rgba(14, 116, 144, 0.12), rgba(79, 70, 229, 0.08)),
    #fff;
  color: #0f766e;
  text-decoration: none;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(15, 20, 25, 0.04));
  transition:
    border-color 0.16s ease,
    box-shadow 0.16s ease,
    transform 0.16s ease;
}

.reviewer-run-cta:hover {
  border-color: rgba(14, 116, 144, 0.44);
  color: #0f766e;
  text-decoration: none;
  box-shadow: 0 10px 26px rgba(14, 116, 144, 0.14);
  transform: translateY(-1px);
}

.reviewer-run-cta strong,
.reviewer-run-cta small {
  display: block;
}

.reviewer-run-cta strong {
  font-size: 0.92rem;
}

.reviewer-run-cta small {
  margin-top: 2px;
  color: var(--text-muted, #8b929e);
  font-size: 0.75rem;
  line-height: 1.35;
}

.reviewer-run-arrow {
  display: grid;
  width: 30px;
  height: 30px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 999px;
  background: #0f766e;
  color: #fff;
  font-weight: 800;
}

@media (max-width: 720px) {
  .reviewer-actions {
    flex-direction: column;
  }

  .reviewer-save-actions {
    align-items: flex-start;
    flex-direction: column;
  }

  .reviewer-run-cta {
    min-width: 0;
    width: 100%;
  }
}
</style>
