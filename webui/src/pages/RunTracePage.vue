<template>
  <section class="panel">
    <h2>Run Trace</h2>
    <div class="row">
      <span class="badge">run_id: {{ runId }}</span>
      <button class="btn-secondary" @click="refresh">刷新</button>
      <RouterLink :to="{ name: 'execution', params: { runId } }">返回执行页</RouterLink>
    </div>
    <p v-if="error" class="error" style="margin-top: 10px">{{ error }}</p>
  </section>

  <section class="panel">
    <h3>Trace Timeline（{{ trace.length }}）</h3>
    <table v-if="trace.length">
      <thead>
        <tr>
          <th>event_type</th>
          <th>actor</th>
          <th>action</th>
          <th>status</th>
          <th>message</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in trace" :key="item.id">
          <td>{{ item.event_type }}</td>
          <td>{{ item.actor }}</td>
          <td>{{ item.action }}</td>
          <td>{{ item.status }}</td>
          <td>{{ item.message }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">暂无 Trace 数据。</p>
  </section>

  <section class="panel">
    <h3>Raw Trace JSON</h3>
    <JsonBlock :data="trace" />
  </section>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import JsonBlock from "../components/JsonBlock.vue";
import { getRunReplay } from "../api";

const props = defineProps({
  runId: { type: String, required: true },
});

const trace = ref([]);
const error = ref("");

async function refresh() {
  error.value = "";
  try {
    const data = await getRunReplay(props.runId);
    trace.value = Array.isArray(data.trace) ? data.trace : [];
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载 Trace 失败";
  }
}

onMounted(refresh);
</script>
