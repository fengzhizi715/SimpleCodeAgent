<template>
  <section class="panel">
    <h2>Run V2 Task</h2>
    <p class="muted">
      提交任务后会跳转到执行页，并自动轮询回放数据。
      <RouterLink to="/history">查看历史运行</RouterLink>
    </p>

    <div class="grid-two">
      <div>
        <label>任务描述</label>
        <textarea v-model="form.task" />
      </div>
      <div>
        <label>系统提示词</label>
        <textarea v-model="form.system_prompt" />
      </div>
    </div>

    <div class="grid-two" style="margin-top: 12px">
      <div>
        <label>Model</label>
        <input v-model="form.model" placeholder="例如 gpt-4.1-mini" />
      </div>
      <div>
        <label>Session ID（可选）</label>
        <input v-model="form.session_id" placeholder="留空自动生成" />
      </div>
      <div>
        <label>工作目录（可选）</label>
        <input v-model="form.workdir" placeholder="/path/to/project" />
      </div>
      <div>
        <label>Max Steps</label>
        <input v-model.number="form.max_steps" type="number" min="1" max="20" />
      </div>
    </div>

    <div class="row" style="margin-top: 14px">
      <button class="btn-primary" :disabled="loading" @click="submitRun">
        {{ loading ? "运行中..." : "开始运行" }}
      </button>
      <span v-if="error" class="error">{{ error }}</span>
    </div>
  </section>
</template>

<script setup>
import { reactive, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { runAgent } from "../api";

const router = useRouter();
const loading = ref(false);
const error = ref("");

const form = reactive({
  task: "请分析当前项目并给出一个小范围优化建议，然后尝试落地。",
  version: "v2",
  model: "",
  session_id: "",
  workdir: "",
  system_prompt: "You are a helpful assistant.",
  max_steps: 8,
  include_trace: false,
});

async function submitRun() {
  error.value = "";
  loading.value = true;
  try {
    const payload = {
      ...form,
      session_id: form.session_id || null,
      workdir: form.workdir || null,
      model: form.model || null,
      temperature: 0,
    };
    const result = await runAgent(payload);
    await router.push({
      name: "execution",
      params: { runId: result.run_id },
      query: { sessionId: result.session_id || "" },
    });
  } catch (err) {
    error.value = err instanceof Error ? err.message : "运行失败";
  } finally {
    loading.value = false;
  }
}
</script>
