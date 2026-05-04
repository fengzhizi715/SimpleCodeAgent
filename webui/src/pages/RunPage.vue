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
      <label class="v2-rag-toggle">
        <input type="checkbox" v-model="form.v2_use_rag" />
        <span>
          <strong>使用 RAG 检索</strong>
          <small>普通项目分析/修复可以关闭；只有需要“根据知识库/文档”回答时再启用。</small>
        </span>
      </label>
      <div class="grid-two" style="margin-bottom: 10px">
        <div :class="{ 'is-disabled-block': !form.v2_use_rag }">
          <label>RAG ID（v2）</label>
          <select v-model="form.rag_id" :disabled="!form.v2_use_rag">
            <option v-for="item in ragCollections" :key="item.rag_id" :value="item.rag_id">
              {{ item.rag_id }} ({{ item.collection_name }})
            </option>
          </select>
          <p class="muted" style="margin: 6px 0 0">
            {{ form.v2_use_rag ? "启用后默认使用 default。" : "已关闭，本次运行不会主动规划 retrieve_docs。" }}
          </p>
        </div>
        <div :class="{ 'is-disabled-block': !form.v2_use_rag }">
          <label>多 RAG 并查（可选）</label>
          <select v-model="selectedRagIds" multiple size="4" :disabled="!form.v2_use_rag">
            <option v-for="item in ragCollections" :key="`multi-${item.rag_id}`" :value="item.rag_id">
              {{ item.rag_id }}
            </option>
          </select>
          <p class="muted" style="margin: 6px 0 0">配置后会把多个知识库一起检索并统一重排。</p>
        </div>
      </div>
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
      <div class="reviewer-config-card" style="margin-top: 10px">
        <label>Coder Agent 模式</label>
        <div class="row" style="margin-top: 6px">
          <label class="v2-agent-option">
            <input
              type="radio"
              name="coding-executor"
              value="internal"
              :checked="form.v2_coding_executor === 'internal'"
              @change="setCodingExecutor('internal')"
            />
            <span>
              <strong>Coder（内置）</strong>
              <small>默认推荐，稳定可控，适合常规小范围改动。</small>
            </span>
          </label>
          <label class="v2-agent-option">
            <input
              type="radio"
              name="coding-executor"
              value="external"
              :checked="form.v2_coding_executor === 'external'"
              @change="setCodingExecutor('external')"
            />
            <span>
              <strong>Coder（外部 CLI）</strong>
              <small>同一 Coder 角色的外部实现，适合复杂编码任务。</small>
            </span>
          </label>
        </div>
        <p class="muted" style="margin: 6px 0 0">
          这里选择的是同一个 <code>Coder Agent</code> 的实现模式，不改变 Planner/Orchestrator 的中心化调度关系。
        </p>
      </div>
      <p class="muted" style="margin: 8px 0 0">
        快速修复可只保留 Analyst + Coder；严格闭环建议启用 Tester，必要时启用 Reviewer。
      </p>
      <div v-if="form.v2_coding_executor === 'external'" class="reviewer-config-card" style="margin-top: 10px">
        <label>Coder（外部 CLI）配置</label>
        <label class="v2-rag-toggle">
          <input type="checkbox" v-model="form.v2_external_coding.enabled" @change="syncExternalCodingAgentSelection" />
          <span>
            <strong>允许 Planner 使用 external coding step</strong>
            <small>默认走模板构建命令，避免让 LLM 直接生成任意 shell 命令。</small>
          </span>
        </label>
        <p class="muted" style="margin: 6px 0 0">
          启用后会自动勾选 <code>external_coder</code>；关闭后自动取消该 Agent。
        </p>
        <div class="grid-two" style="margin-top: 8px">
          <div>
            <label>偏好外部 Agent</label>
            <select v-model="form.v2_external_coding.preferred_agent">
              <option value="codex_cli">codex_cli</option>
              <option value="cursor_cli">cursor_cli</option>
            </select>
          </div>
          <div>
            <label>允许 raw external_command</label>
            <select v-model="form.v2_external_coding.allow_raw_external_command">
              <option :value="false">否（推荐）</option>
              <option :value="true">是（高风险）</option>
            </select>
          </div>
          <div>
            <label>Codex 模板</label>
            <input v-model="form.v2_external_coding.codex_template" placeholder="codex exec --sandbox workspace-write {prompt}" />
          </div>
          <div>
            <label>Cursor 模板</label>
            <input v-model="form.v2_external_coding.cursor_template" placeholder="cursor-agent --trust {prompt}" />
          </div>
          <p class="muted grid-span-2" style="margin: 0">
            默认从服务进程的 PATH 解析外部 CLI；Codex 会自动使用 <code>workspace-write</code>，
            Cursor 后端非交互运行会自动补 <code>--trust</code>。
            如需固定路径，可在服务环境中配置 <code>CURSOR_CLI_PATH</code> 或 <code>CODEX_CLI_PATH</code>。
          </p>
        </div>
      </div>
      <p v-else class="muted" style="margin-top: 10px">
        当前为 Coder（内置）模式，已隐藏外部 CLI 配置。
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
import { listRagCollections, runAgent } from "../api";
import { loadReviewStrategy } from "../reviewerConfig";

const router = useRouter();
const loading = ref(false);
const error = ref("");
const v1Result = ref(null);
const ragCollections = ref([{ rag_id: "default", collection_name: "codeagent_docs" }]);
const selectedRagIds = ref([]);
const defaultV2Agents = ["planner", "analyst", "coder", "external_coder", "tester", "reviewer"];
const configurableV2Agents = [
  { id: "analyst", label: "Analyst", help: "识别项目结构和关键文件" },
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
  v2_enabled_agents: ["planner", "analyst", "coder", "tester", "reviewer"],
  v2_coding_executor: "internal",
  v2_review_strategy: loadReviewStrategy(),
  v2_use_rag: false,
  rag_id: "default",
  v2_external_coding: {
    enabled: false,
    preferred_agent: "codex_cli",
    allow_raw_external_command: false,
    codex_template: "codex exec --sandbox workspace-write {prompt}",
    cursor_template: "cursor-agent --trust {prompt}",
    cursor_cli_path: "",
    codex_cli_path: "",
  },
});

onMounted(() => {
  form.v2_review_strategy = loadReviewStrategy();
  syncExternalCodingAgentSelection();
  void loadRagCollections();
});

async function loadRagCollections() {
  try {
    const data = await listRagCollections();
    const items = Array.isArray(data?.items) ? data.items : [];
    if (items.length) {
      ragCollections.value = items;
      if (!items.some((item) => item.rag_id === form.rag_id)) {
        form.rag_id = items[0].rag_id;
      }
    }
  } catch {
    ragCollections.value = [{ rag_id: "default", collection_name: "codeagent_docs" }];
  }
}

function toggleV2Agent(agentId) {
  const selected = new Set(form.v2_enabled_agents);
  if (selected.has(agentId)) {
    selected.delete(agentId);
  } else {
    selected.add(agentId);
  }
  selected.add("planner");
  form.v2_enabled_agents = defaultV2Agents.filter((id) => selected.has(id));
  syncExternalCodingAgentSelection();
}

function resetV2Agents() {
  form.v2_coding_executor = "internal";
  form.v2_enabled_agents = ["planner", "analyst", "coder", "tester", "reviewer"];
  syncExternalCodingAgentSelection();
}

function setCodingExecutor(mode) {
  form.v2_coding_executor = mode;
  if (mode === "external") {
    form.v2_external_coding.enabled = true;
  }
  syncExternalCodingAgentSelection();
}

function syncExternalCodingAgentSelection() {
  const selected = new Set(form.v2_enabled_agents);
  if (form.v2_coding_executor === "external") {
    selected.delete("coder");
    selected.add("external_coder");
  } else {
    selected.add("coder");
    selected.delete("external_coder");
    form.v2_external_coding.enabled = false;
  }
  selected.add("planner");
  form.v2_enabled_agents = defaultV2Agents.filter((id) => selected.has(id));
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
      syncExternalCodingAgentSelection();
      if (form.v2_coding_executor === "external" && !form.v2_external_coding.enabled) {
        error.value = "外部 CLI 模式需要开启 external coding step。";
        return;
      }
      if (form.v2_coding_executor !== "external" && form.v2_external_coding.enabled) {
        error.value = "请先选择外部 CLI 模式，再开启 external coding step。";
        return;
      }
      payload.v2_use_rag = Boolean(form.v2_use_rag);
      if (form.v2_use_rag) {
        payload.rag_id = form.rag_id?.trim() || "default";
        const ragIds = selectedRagIds.value
          .map((item) => String(item).trim())
          .filter(Boolean);
        if (ragIds.length) {
          payload.rag_ids = ragIds;
        }
      }
      payload.v2_enabled_agents = [...form.v2_enabled_agents];
      payload.v2_external_coding = {
        ...form.v2_external_coding,
        enabled: form.v2_coding_executor === "external",
      };
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
