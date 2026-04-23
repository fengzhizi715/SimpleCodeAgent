<template>
  <section class="panel">
    <h2>V2 运行历史</h2>
    <p class="muted">
      仅展示已落库且含 <code>workspace</code> 快照的 V2 运行（与 <code>GET /debug/v2/runs</code> 一致）。
    </p>
    <div class="row" style="margin-bottom: 12px">
      <button class="btn-secondary" :disabled="loading" @click="load">刷新</button>
      <RouterLink to="/">新建任务</RouterLink>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
  </section>

  <section class="panel" v-if="runs.length">
    <table>
      <thead>
        <tr>
          <th>状态</th>
          <th>run_id</th>
          <th>目标（user_goal）</th>
          <th>更新时间</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in runs" :key="r.run_id">
          <td>{{ r.status }}</td>
          <td class="mono">{{ shortId(r.run_id) }}</td>
          <td>{{ truncate(r.user_goal || r.task, 80) }}</td>
          <td class="muted">{{ r.updated_at }}</td>
          <td>
            <RouterLink :to="{ name: 'execution', params: { runId: r.run_id } }">详情</RouterLink>
            ·
            <RouterLink :to="{ name: 'trace', params: { runId: r.run_id } }">Trace</RouterLink>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
  <section v-else-if="!loading && !error" class="panel muted">暂无历史记录。</section>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { listV2Runs } from "../api";

const runs = ref([]);
const loading = ref(false);
const error = ref("");

function shortId(id) {
  if (!id || id.length <= 12) return id;
  return `${id.slice(0, 8)}…`;
}

function truncate(s, n) {
  if (!s) return "";
  return s.length <= n ? s : `${s.slice(0, n)}…`;
}

async function load() {
  error.value = "";
  loading.value = true;
  try {
    const data = await listV2Runs({ limit: 100, offset: 0 });
    runs.value = Array.isArray(data.runs) ? data.runs : [];
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
    runs.value = [];
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.mono {
  font-family: ui-monospace, monospace;
  font-size: 12px;
}
</style>
