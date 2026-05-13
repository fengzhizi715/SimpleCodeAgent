<template>
  <section class="panel">
    <h2>新建运行任务</h2>
    <p class="muted">
      选择版本后提交任务：<code>v2</code> 与 <code>v3</code> 会跳转执行详情页；<code>v1</code> 会在当前页直接展示结果。
      <code>v3</code> 的 <code>plan_only</code> 仍会在当前页直接展示结构化结果。<RouterLink to="/history">查看历史运行</RouterLink>
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
          <option value="v3">v3（Graph + Skill + Trigger）</option>
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
              : form.version === "v3"
                ? "v3：当前 MVP 主要由 graph 与 trigger 收敛，max_steps 主要保留给统一接口兼容。"
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

    <div v-else-if="form.version === 'v3'" class="v2-agent-config">
      <div class="v2-agent-config-head">
        <div>
          <label>V3 运行模式</label>
          <p class="muted">v3 会围绕 planning、graph inspection、execution report 和本地 event/trigger 输出结构化结果。</p>
        </div>
      </div>
      <div class="review-rule-grid" style="margin-top: 12px">
        <label class="review-rule-option">
          <input type="checkbox" v-model="form.plan_only" />
          <span>
            <strong>只生成计划</strong>
            <small>只返回 planning 和 graph inspection，不执行 graph。</small>
          </span>
        </label>
        <label class="review-rule-option">
          <input type="checkbox" v-model="form.include_events" />
          <span>
            <strong>返回事件列表</strong>
            <small>把本次 graph / trigger 的本地事件一起带回前端。</small>
          </span>
        </label>
        <label class="review-rule-option">
          <input type="checkbox" v-model="form.include_trace" />
          <span>
            <strong>返回简版 Trace</strong>
            <small>在响应中附带已格式化前的原始 trace 事件，便于调试。</small>
          </span>
        </label>
      </div>
      <label class="v2-rag-toggle" style="margin-top: 12px">
        <input type="checkbox" v-model="form.v3_use_rag" />
        <span>
          <strong>为 V3 图增加 RAG 检索节点</strong>
          <small>启用后 planner 可以生成 <code>retrieve_docs -&gt; analyze_repo -&gt; ...</code> 这样的结构。</small>
        </span>
      </label>
      <div class="grid-two" style="margin-top: 10px">
        <div :class="{ 'is-disabled-block': !form.v3_use_rag }">
          <label>RAG ID（v3）</label>
          <select v-model="form.v3_rag_id" :disabled="!form.v3_use_rag">
            <option v-for="item in ragCollections" :key="`v3-${item.rag_id}`" :value="item.rag_id">
              {{ item.rag_id }} ({{ item.collection_name }})
            </option>
          </select>
          <p class="muted" style="margin: 6px 0 0">
            {{ form.v3_use_rag ? "启用后 planner 会把该知识库作为 retrieve_docs 的候选来源。" : "关闭后 v3 默认不注入 RAG 检索节点。" }}
          </p>
        </div>
        <div :class="{ 'is-disabled-block': !form.v3_use_rag }">
          <label>多 RAG 并查（v3，可选）</label>
          <select v-model="selectedV3RagIds" multiple size="4" :disabled="!form.v3_use_rag">
            <option v-for="item in ragCollections" :key="`v3-multi-${item.rag_id}`" :value="item.rag_id">
              {{ item.rag_id }}
            </option>
          </select>
          <p class="muted" style="margin: 6px 0 0">配置后 retrieve_docs skill 会在多个知识库中统一检索与重排。</p>
        </div>
      </div>
      <div class="reviewer-config-card" style="margin-top: 12px">
        <label>V3 Coding Backend</label>
        <div class="row" style="margin-top: 6px">
          <label class="v2-agent-option">
            <input
              type="radio"
              name="v3-coding-executor"
              value="internal"
              :checked="form.v3_coding_executor === 'internal'"
              @change="setV3CodingExecutor('internal')"
            />
            <span>
              <strong>Internal coder</strong>
              <small>走内置 coder 通路，适合默认的小范围修复。</small>
            </span>
          </label>
          <label class="v2-agent-option">
            <input
              type="radio"
              name="v3-coding-executor"
              value="external"
              :checked="form.v3_coding_executor === 'external'"
              @change="setV3CodingExecutor('external')"
            />
            <span>
              <strong>External coder</strong>
              <small>把 <code>coding</code> skill 切到外部 CLI 后端，适合更复杂的编码任务。</small>
            </span>
          </label>
        </div>
        <p class="muted" style="margin: 6px 0 0">
          在 v3 里这不是“另一个 Agent”，而是同一个 <code>coding skill</code> 的不同执行后端。
        </p>
      </div>
      <div v-if="form.v3_coding_executor === 'external'" class="reviewer-config-card" style="margin-top: 10px">
        <label>V3 External Coding 配置</label>
        <div class="grid-two" style="margin-top: 8px">
          <div>
            <label>偏好外部 Agent</label>
            <select v-model="form.v3_external_coding.preferred_agent">
              <option value="codex_cli">codex_cli</option>
              <option value="cursor_cli">cursor_cli</option>
            </select>
          </div>
          <div>
            <label>允许 raw external_command</label>
            <select v-model="form.v3_external_coding.allow_raw_external_command">
              <option :value="false">否（推荐）</option>
              <option :value="true">是（高风险）</option>
            </select>
          </div>
          <div>
            <label>Codex 模板</label>
            <input v-model="form.v3_external_coding.codex_template" placeholder="codex exec --sandbox workspace-write {prompt}" />
          </div>
          <div>
            <label>Cursor 模板</label>
            <input v-model="form.v3_external_coding.cursor_template" placeholder="cursor-agent --trust {prompt}" />
          </div>
          <p class="muted grid-span-2" style="margin: 0">
            当前配置会作为 <code>coding skill</code> 的 external backend 选项传给后端，不会改变 v3 的 graph / trigger 语义。
          </p>
        </div>
      </div>
      <p class="muted" style="margin: 10px 0 0">
        当前页面主要覆盖 v3 MVP：<code>Skill + TaskGraph + ExecutionKernel + Basic Event/Trigger</code>。
      </p>
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
        {{ loading ? "运行中..." : form.version === "v3" && form.plan_only ? "生成计划" : "开始运行" }}
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

  <template v-if="v3Result">
    <section class="panel">
      <h3>V3 运行结果</h3>
      <p class="muted">
        version: <code>{{ v3Result.version }}</code>
        <span v-if="v3Result.run_id"> · run_id: <code>{{ v3Result.run_id }}</code></span>
        <span v-if="v3Result.session_id"> · session_id: <code>{{ v3Result.session_id }}</code></span>
        <span v-if="v3Result.status"> · status: <code>{{ v3Result.status }}</code></span>
      </p>
      <table>
        <tbody>
          <tr><th>plan_only</th><td>{{ v3Result.report ? "false" : "true" }}</td></tr>
          <tr><th>step_count</th><td>{{ v3Result.step_count ?? 0 }}</td></tr>
          <tr><th>planning.template</th><td>{{ v3Result.planning?.template_name || "—" }}</td></tr>
          <tr><th>planning.recovery_strategy</th><td>{{ v3Result.planning?.recovery_strategy || "—" }}</td></tr>
          <tr><th>planning.coding_mode</th><td>{{ v3Result.planning?.coding_execution_mode || "—" }}</td></tr>
          <tr><th>planning.rag_ids</th><td>{{ formatRagIds(v3Result.planning?.rag_ids, v3Result.planning?.rag_id) }}</td></tr>
          <tr><th>inspection.layers</th><td>{{ formatExecutionLayers(v3Result.inspection?.execution_layers) }}</td></tr>
          <tr><th>events</th><td>{{ Array.isArray(v3Result.events) ? v3Result.events.length : 0 }}</td></tr>
          <tr><th>trace</th><td>{{ Array.isArray(v3Result.trace) ? v3Result.trace.length : 0 }}</td></tr>
        </tbody>
      </table>
    </section>

    <section v-if="v3Result.planning" class="panel">
      <h3>Planning</h3>
      <p class="muted">
        {{ v3Result.planning.template_reason || "Planner 已返回结构化 graph 计划。" }}
      </p>
      <table>
        <tbody>
          <tr><th>goal_kind</th><td>{{ v3Result.planning.goal_kind || "—" }}</td></tr>
          <tr><th>repo_profile</th><td>{{ v3Result.planning.repo_profile || "—" }}</td></tr>
          <tr><th>template_name</th><td>{{ v3Result.planning.template_name || "—" }}</td></tr>
          <tr><th>recovery_strategy</th><td>{{ v3Result.planning.recovery_strategy || "—" }}</td></tr>
          <tr><th>coding_execution_mode</th><td>{{ v3Result.planning.coding_execution_mode || "—" }}</td></tr>
          <tr><th>rag_ids</th><td>{{ formatRagIds(v3Result.planning.rag_ids, v3Result.planning.rag_id) }}</td></tr>
        </tbody>
      </table>
      <div v-if="planningNodes(v3Result.planning).length" class="planning-node-section">
        <div class="planning-node-head">
          <h4>Graph Nodes</h4>
          <p class="muted">按 planner 生成顺序展示节点、依赖与关键输入，方便快速扫一眼执行骨架。</p>
        </div>
        <div class="planning-node-list">
          <article
            v-for="(node, index) in planningNodes(v3Result.planning)"
            :key="node.node_id || index"
            class="planning-node-card"
          >
            <div class="planning-node-top">
              <div class="planning-node-title">
                <span class="planning-node-index">#{{ index + 1 }}</span>
                <strong>{{ node.node_id }}</strong>
              </div>
              <span class="agent-version agent-version--v3">{{ node.skill_name }}</span>
            </div>
            <p class="planning-node-deps muted">
              depends on:
              <span v-if="node.dependencies?.length">{{ node.dependencies.join(", ") }}</span>
              <span v-else>—</span>
            </p>
            <table class="planning-node-table">
              <tbody>
                <tr v-if="node.input_payload?.goal">
                  <th>goal</th>
                  <td>{{ node.input_payload.goal }}</td>
                </tr>
                <tr v-if="node.input_payload?.command">
                  <th>command</th>
                  <td><code>{{ node.input_payload.command }}</code></td>
                </tr>
                <tr v-if="node.input_payload?.query">
                  <th>query</th>
                  <td>{{ node.input_payload.query }}</td>
                </tr>
                <tr v-if="node.input_payload?.execution_mode">
                  <th>mode</th>
                  <td>{{ node.input_payload.execution_mode }}</td>
                </tr>
                <tr v-if="node.input_payload?.rag_id || (Array.isArray(node.input_payload?.rag_ids) && node.input_payload.rag_ids.length)">
                  <th>rag</th>
                  <td>{{ formatRagIds(node.input_payload.rag_ids, node.input_payload.rag_id) }}</td>
                </tr>
              </tbody>
            </table>
          </article>
        </div>
      </div>
      <JsonBlock :data="v3Result.planning" />
    </section>

    <section v-if="v3Result.inspection" class="panel">
      <h3>Graph Inspection</h3>
      <p class="muted">execution_layers 会帮助前端直观看到这次 graph 的层级结构。</p>
      <JsonBlock :data="v3Result.inspection" />
    </section>

    <section v-if="v3Result.report" class="panel">
      <h3>Execution Report</h3>
      <p class="muted">
        graph_id: <code>{{ v3Result.report.graph_id }}</code>
        · execution_nodes: <code>{{ v3Result.report.execution_nodes?.length || 0 }}</code>
        · trigger_diagnostics: <code>{{ v3Result.report.trigger_diagnostics?.length || 0 }}</code>
      </p>
      <JsonBlock :data="v3Result.report" />
    </section>

    <section v-if="Array.isArray(v3Result.events) && v3Result.events.length" class="panel">
      <h3>Events</h3>
      <JsonBlock :data="v3Result.events" />
    </section>

    <section v-if="Array.isArray(v3Result.trace) && v3Result.trace.length" class="panel">
      <h3>Trace</h3>
      <JsonBlock :data="v3Result.trace" />
    </section>
  </template>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import JsonBlock from "../components/JsonBlock.vue";
import { listRagCollections, runAgent } from "../api";
import { loadReviewStrategy } from "../reviewerConfig";

const router = useRouter();
const loading = ref(false);
const error = ref("");
const v1Result = ref(null);
const v3Result = ref(null);
const ragCollections = ref([{ rag_id: "default", collection_name: "codeagent_docs" }]);
const selectedRagIds = ref([]);
const selectedV3RagIds = ref([]);
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
  include_events: true,
  plan_only: false,
  v3_use_rag: false,
  v3_rag_id: "default",
  v3_coding_executor: "internal",
  v3_external_coding: {
    preferred_agent: "codex_cli",
    allow_raw_external_command: false,
    codex_template: "codex exec --sandbox workspace-write {prompt}",
    cursor_template: "cursor-agent --trust {prompt}",
    cursor_cli_path: "",
    codex_cli_path: "",
  },
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
      if (!items.some((item) => item.rag_id === form.v3_rag_id)) {
        form.v3_rag_id = items[0].rag_id;
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

function setV3CodingExecutor(mode) {
  form.v3_coding_executor = mode;
}

function formatExecutionLayers(layers) {
  if (!Array.isArray(layers) || !layers.length) {
    return "—";
  }
  return layers.map((layer) => `[${layer.join(", ")}]`).join(" -> ");
}

function formatRagIds(ragIds, ragId) {
  if (Array.isArray(ragIds) && ragIds.length) {
    return ragIds.join(", ");
  }
  if (ragId) {
    return String(ragId);
  }
  return "—";
}

function planningNodes(planning) {
  const nodes = planning?.graph?.nodes;
  return Array.isArray(nodes) ? nodes : [];
}

async function submitRun() {
  error.value = "";
  v1Result.value = null;
  v3Result.value = null;
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
    } else if (form.version === "v3") {
      payload.include_events = Boolean(form.include_events);
      payload.plan_only = Boolean(form.plan_only);
      payload.v3_coding_execution_mode = form.v3_coding_executor;
      if (form.v3_use_rag) {
        payload.rag_id = form.v3_rag_id?.trim() || "default";
        const ragIds = selectedV3RagIds.value
          .map((item) => String(item).trim())
          .filter(Boolean);
        if (ragIds.length) {
          payload.rag_ids = ragIds;
        }
      }
      if (form.v3_coding_executor === "external") {
        payload.v2_external_coding = {
          ...form.v3_external_coding,
          enabled: true,
        };
      }
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
    if (form.version === "v3") {
      if (!form.plan_only && result.run_id) {
        await router.push({
          name: "execution",
          params: { runId: result.run_id },
          query: { version: "v3", sessionId: result.session_id || "" },
        });
        return;
      }
      v3Result.value = result;
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
