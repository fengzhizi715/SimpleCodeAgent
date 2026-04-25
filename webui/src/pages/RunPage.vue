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
      <div>
        <label>运行超时（秒）</label>
        <input v-model.number="form.run_timeout_seconds" type="number" min="10" max="1800" />
        <p class="muted" style="margin: 6px 0 0">
          超时后系统会主动结束本次运行，避免复杂任务长时间阻塞。
        </p>
      </div>
    </div>

    <div v-if="form.version === 'v1'" style="margin-top: 12px">
      <label>System Prompt（v1）</label>
      <textarea v-model="form.system_prompt" />
    </div>
    <div v-else class="v2-agent-config">
      <div class="v2-agent-config-head">
        <div>
          <label>V2 Agent 配置</label>
          <p class="muted">Orchestrator / Planner 始终启用；其余 Agent 可按本次运行选择。</p>
        </div>
        <button type="button" class="btn-secondary btn-sm" @click="resetV2Agents">恢复默认</button>
      </div>
      <div class="v2-agent-options">
        <label class="v2-agent-option is-locked">
          <input type="checkbox" checked disabled />
          <span>
            <strong>Orchestrator</strong>
            <small>中心化调度，必选</small>
          </span>
        </label>
        <label class="v2-agent-option is-locked">
          <input type="checkbox" checked disabled />
          <span>
            <strong>Planner</strong>
            <small>生成计划，必选</small>
          </span>
        </label>
        <label v-for="agent in configurableV2Agents" :key="agent.id" class="v2-agent-option">
          <input
            type="checkbox"
            :checked="form.v2_enabled_agents.includes(agent.id)"
            @change="toggleV2Agent(agent.id)"
          />
          <span>
            <strong>{{ agent.label }}</strong>
            <small>{{ agent.help }}</small>
          </span>
        </label>
      </div>
      <p class="muted" style="margin: 8px 0 0">
        快速修复可只保留 Analyst + Coder；严格闭环建议启用 Tester，必要时启用 Reviewer。
      </p>

      <div v-if="form.v2_enabled_agents.includes('reviewer')" class="reviewer-config-card">
        <label>Reviewer 策略</label>
        <p class="muted">
          当前使用 `/agents` 中保存的 Reviewer 配置：
          严格度 <code>{{ form.v2_review_strategy.strictness }}</code>，
          测试失败 <code>{{ form.v2_review_strategy.test_failure_mode }}</code>，
          规则分组 {{ form.v2_review_strategy.rule_groups.length }} 个。
        </p>
        <RouterLink class="btn-secondary btn-sm" to="/agents?agent=reviewer">前往配置 Reviewer</RouterLink>
      </div>
    </div>

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
import { onMounted, reactive, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { runAgent } from "../api";
import { loadReviewStrategy } from "../reviewerConfig";

const router = useRouter();
const loading = ref(false);
const error = ref("");
const v1Result = ref(null);
const defaultV2Agents = ["planner", "analyst", "coder", "tester", "reviewer"];
const configurableV2Agents = [
  { id: "analyst", label: "Analyst", help: "识别项目结构和关键文件" },
  { id: "coder", label: "Coder", help: "根据上下文修改代码" },
  { id: "tester", label: "Tester", help: "运行编译/测试验证" },
  { id: "reviewer", label: "Reviewer", help: "检查 patch 风险" },
];

const form = reactive({
  task: "",
  version: "v2",
  model: "",
  session_id: "",
  workdir: "",
  max_steps: 8,
  run_timeout_seconds: 180,
  include_trace: false,
  system_prompt: "You are a helpful assistant.",
  v2_enabled_agents: [...defaultV2Agents],
  v2_review_strategy: loadReviewStrategy(),
});

onMounted(() => {
  form.v2_review_strategy = loadReviewStrategy();
});

function toggleV2Agent(agentId) {
  const selected = new Set(form.v2_enabled_agents);
  if (selected.has(agentId)) {
    selected.delete(agentId);
  } else {
    selected.add(agentId);
  }
  selected.add("planner");
  form.v2_enabled_agents = defaultV2Agents.filter((id) => selected.has(id));
}

function resetV2Agents() {
  form.v2_enabled_agents = [...defaultV2Agents];
}

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
      run_timeout_seconds: form.run_timeout_seconds,
      session_id: form.session_id || null,
      workdir: form.workdir || null,
      model: form.model || null,
      temperature: 0,
    };
    if (form.version === "v1") {
      payload.system_prompt = form.system_prompt;
    } else {
      payload.v2_enabled_agents = [...form.v2_enabled_agents];
      if (form.v2_enabled_agents.includes("reviewer")) {
        payload.v2_review_strategy = loadReviewStrategy();
      }
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
