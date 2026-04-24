<template>
  <section class="panel">
    <h2>智能体列表</h2>
    <p class="muted">只读视图：展示当前运行时注册的智能体与能力，不提供编辑操作。</p>

    <div class="row agents-toolbar">
      <span class="badge">总数：{{ totalLabel }}</span>
    </div>

    <p v-if="errorMsg" class="error">{{ errorMsg }}</p>

    <p v-if="!loading && !agents.length" class="muted">暂无智能体数据。</p>

    <div v-else class="agents-grid">
      <article v-for="agent in agents" :key="agent.agent_id" class="agent-card">
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
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { listAgents } from "../api";

const loading = ref(false);
const errorMsg = ref("");
const agents = ref([]);
const total = ref(0);

const totalLabel = computed(() => (typeof total.value === "number" ? `${total.value} 个` : "—"));

async function loadAgents() {
  loading.value = true;
  errorMsg.value = "";
  try {
    const data = await listAgents();
    agents.value = Array.isArray(data.agents) ? data.agents : [];
    total.value = typeof data.total === "number" ? data.total : agents.value.length;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    errorMsg.value = message || "加载智能体列表失败。";
    agents.value = [];
    total.value = 0;
  } finally {
    loading.value = false;
  }
}

onMounted(loadAgents);
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
</style>
