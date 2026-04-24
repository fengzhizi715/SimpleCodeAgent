<template>
  <section class="panel">
    <h2>新建运行任务</h2>
    <p class="muted">
      选择版本后提交任务：<code>v2</code> 会跳转执行页并轮询回放；<code>v1</code> 会在当前页直接展示结果。
      <RouterLink to="/history">查看历史运行</RouterLink>
    </p>

    <div>
      <label>任务描述</label>
      <textarea
        v-model="form.task"
        placeholder="例如：先分析当前项目结构，再给出一个可落地的小范围优化建议。"
      />
      <p class="muted" style="margin: 6px 0 0">
        请直接描述你的目标与约束（如技术栈、改动范围、是否需要运行测试）。
      </p>
    </div>

    <div class="grid-two" style="margin-top: 12px">
      <div>
        <label>版本</label>
        <select v-model="form.version">
          <option value="v1">v1（单 Agent）</option>
          <option value="v2">v2（多 Agent）</option>
        </select>
      </div>
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
        <p class="muted" style="margin: 6px 0 0">
          {{
            form.version === "v2"
              ? "v2：用于限制多 Agent 委派与重规划步数，避免运行过长。"
              : "v1：用于限制单 Agent 主循环步数，建议先从 3~8 步开始。"
          }}
        </p>
      </div>
    </div>

    <div v-if="form.version === 'v1'" style="margin-top: 12px">
      <label>System Prompt（v1）</label>
      <textarea v-model="form.system_prompt" />
    </div>
    <p v-else class="muted" style="margin: 12px 0 0">
      v2 采用内置的多 Agent 角色提示词，由编排器统一管理；当前页面不提供自定义 System Prompt。
    </p>

    <div class="row" style="margin-top: 14px">
      <button class="btn-primary" :disabled="loading" @click="submitRun">
        {{ loading ? "运行中..." : "开始运行" }}
      </button>
      <span v-if="error" class="error">{{ error }}</span>
    </div>
  </section>

  <section v-if="v1Result" class="panel">
    <h3>V1 运行结果</h3>
    <p class="muted">
      run_id: <code>{{ v1Result.run_id }}</code> · session_id: <code>{{ v1Result.session_id }}</code>
    </p>
    <pre>{{ v1Result.answer }}</pre>
  </section>
</template>

<script setup>
import { reactive, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { runAgent } from "../api";

const router = useRouter();
const loading = ref(false);
const error = ref("");
const v1Result = ref(null);

const form = reactive({
  task: "",
  version: "v2",
  model: "",
  session_id: "",
  workdir: "",
  max_steps: 8,
  include_trace: false,
  system_prompt: "You are a helpful assistant.",
});

async function submitRun() {
  error.value = "";
  v1Result.value = null;
  loading.value = true;
  try {
    const payload = {
      task: form.task,
      version: form.version,
      include_trace: form.include_trace,
      max_steps: form.max_steps,
      session_id: form.session_id || null,
      workdir: form.workdir || null,
      model: form.model || null,
      temperature: 0,
    };
    if (form.version === "v1") {
      payload.system_prompt = form.system_prompt;
    }
    const result = await runAgent(payload);
    if (form.version === "v2") {
      await router.push({
        name: "execution",
        params: { runId: result.run_id },
        query: { sessionId: result.session_id || "" },
      });
      return;
    }
    v1Result.value = result;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "运行失败";
  } finally {
    loading.value = false;
  }
}
</script>
