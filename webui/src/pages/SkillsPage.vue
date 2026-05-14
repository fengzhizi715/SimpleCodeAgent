<template>
  <section class="panel">
    <h2>Skills 列表</h2>
    <p class="muted">
      展示当前运行时注册的 v3 skills，以及它们在 `PlanningSkill` 生成图时常出现的模板位置。
    </p>

    <div class="row agents-toolbar">
      <span class="badge">总数：{{ totalLabel }}</span>
    </div>

    <p v-if="errorMsg" class="error">{{ errorMsg }}</p>
    <p v-if="!loading && !skills.length" class="muted">暂无 v3 skill 数据。</p>

    <div v-else class="agents-grid skills-grid">
      <article
        v-for="skill in skills"
        :key="skill.skill_name"
        class="agent-card skill-card"
      >
        <header class="agent-card-head">
          <code class="agent-id">{{ skill.skill_name }}</code>
          <span class="badge" :class="skill.enabled ? 'badge-enabled' : 'badge-disabled'">
            {{ skill.enabled ? "enabled" : "disabled" }}
          </span>
        </header>
        <p class="agent-role">{{ skill.skill_type || "—" }}</p>
        <p class="agent-desc">{{ skill.description || "—" }}</p>
        <div class="agent-caps">
          <strong>典型用途</strong>
          <p class="muted">{{ skill.typical_use || "—" }}</p>
        </div>
        <div class="agent-caps">
          <strong>所在模板</strong>
          <div v-if="skill.template_names?.length" class="template-badge-list">
            <button
              v-for="templateName in skill.template_names"
              :key="`${skill.skill_name}-${templateName}`"
              type="button"
              class="template-badge"
              :class="{ 'is-active': selectedTemplateName === templateName }"
              @click="selectTemplate(templateName)"
            >
              {{ templateName }}
            </button>
          </div>
          <p v-else class="muted">—</p>
        </div>
        <div class="agent-caps">
          <strong>能力</strong>
          <p v-if="skill.capabilities?.length" class="muted">{{ skill.capabilities.join(" / ") }}</p>
          <p v-else class="muted">—</p>
        </div>
      </article>
    </div>

    <section v-if="selectedTemplateInfo" class="template-panel">
      <div class="template-panel-head">
        <div>
          <h3>{{ selectedTemplateInfo.label }}</h3>
          <p class="muted">{{ selectedTemplateInfo.summary }}</p>
        </div>
        <span class="badge">Template</span>
      </div>
      <div class="template-panel-grid">
        <article class="template-panel-card">
          <h4>典型场景</h4>
          <p class="muted">{{ selectedTemplateInfo.whenToUse }}</p>
        </article>
        <article class="template-panel-card">
          <h4>常见节点结构</h4>
          <pre class="template-flow-pre">{{ selectedTemplateInfo.flow }}</pre>
        </article>
      </div>
    </section>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { listAgents } from "../api";

const route = useRoute();
const router = useRouter();
const loading = ref(false);
const errorMsg = ref("");
const skills = ref([]);
const selectedTemplateName = ref("");

const totalLabel = computed(() => `${skills.value.length} 个`);
const templateCatalog = {
  analysis_only: {
    label: "analysis_only",
    summary: "只做仓库理解，不进入改码或测试执行。",
    whenToUse: "适合需求澄清、阅读代码、看模块边界，或者先建立仓库画像的场景。",
    flow: "analyze_repo",
  },
  analysis_with_context: {
    label: "analysis_with_context",
    summary: "先补文档/RAG 上下文，再做仓库分析。",
    whenToUse: "适合需求依赖外部文档、知识库或 API 说明，且当前任务先以理解为主的场景。",
    flow: "retrieve_docs -> analyze_repo",
  },
  testing_branch_verify: {
    label: "testing_branch_verify",
    summary: "把验证拆成多个 focused test 分支，最后再 join 到 full suite。",
    whenToUse: "适合想先暴露局部失败，再看整体测试收敛情况的场景。",
    flow: "analyze_repo -> test_scope_1 + test_scope_2 -> test_full_suite",
  },
  coding_focus_then_full_suite: {
    label: "coding_focus_then_full_suite",
    summary: "先改码，再跑小范围验证，最后再跑全量测试。",
    whenToUse: "适合局部修改、希望更快拿到反馈，同时最终仍要确认全量回归的场景。",
    flow: "analyze_repo -> coding -> test_changed_scope -> test_full_suite",
  },
  default: {
    label: "default",
    summary: "默认线性模板，按分析、改码、验证的顺序往前走。",
    whenToUse: "适合没有明显 branch/join 需求、目标比较直接的小范围编码任务。",
    flow: "analyze_repo -> coding -> test_runner",
  },
  template_fix_after_test_failed: {
    label: "template_fix_after_test_failed",
    summary: "测试失败后触发一次 fix-only 修复动作，不自动重跑完整验证。",
    whenToUse: "适合希望先完成最小修复、后续再由人工或别的流程决定是否复验的场景。",
    flow: "test_failed -> coding",
  },
  template_fix_and_retest_after_test_failed: {
    label: "template_fix_and_retest_after_test_failed",
    summary: "测试失败后进入受控的 fix -> re-test 恢复链。",
    whenToUse: "适合想让系统自动尝试恢复，并把是否真正收敛验证清楚的场景。",
    flow: "test_failed -> tdd -> coding -> re-test",
  },
};

const selectedTemplateInfo = computed(() => {
  const key = String(selectedTemplateName.value || "").trim();
  if (!key) {
    return null;
  }
  return templateCatalog[key] || {
    label: key,
    summary: "当前模板说明尚未补齐，但它已经被 planner 或 trigger 用于图执行。",
    whenToUse: "适合需要进一步补充教学说明的模板。",
    flow: key,
  };
});

async function loadSkills() {
  loading.value = true;
  errorMsg.value = "";
  try {
    const data = await listAgents();
    skills.value = Array.isArray(data.v3_skills) ? data.v3_skills : [];
    if (!selectedTemplateName.value) {
      const firstTemplate = skills.value.find((item) => Array.isArray(item.template_names) && item.template_names.length)
        ?.template_names?.[0];
      selectedTemplateName.value = firstTemplate || "";
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    errorMsg.value = message || "加载 skills 列表失败。";
    skills.value = [];
  } finally {
    loading.value = false;
  }
}

function selectTemplate(templateName) {
  selectedTemplateName.value = templateName;
  router.replace({ path: "/skills", query: { template: templateName } });
}

onMounted(() => {
  const queryTemplate = String(route.query.template || "").trim();
  if (queryTemplate) {
    selectedTemplateName.value = queryTemplate;
  }
  loadSkills();
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
}

.skill-card {
  background:
    linear-gradient(180deg, rgba(248, 250, 252, 0.94) 0%, rgba(238, 242, 255, 0.94) 100%);
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
  text-transform: none;
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

.template-badge-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.template-badge {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 5px 10px;
  border-radius: 999px;
  border: 1px solid rgba(79, 70, 229, 0.16);
  background: rgba(79, 70, 229, 0.06);
  color: #4338ca;
  font-size: 0.75rem;
  font-weight: 700;
}

.template-badge.is-active {
  background: rgba(79, 70, 229, 0.14);
  border-color: rgba(79, 70, 229, 0.34);
  box-shadow: 0 6px 18px rgba(79, 70, 229, 0.12);
}

.template-panel {
  margin-top: 18px;
  border: 1px solid rgba(79, 70, 229, 0.12);
  border-radius: 14px;
  background:
    linear-gradient(135deg, rgba(79, 70, 229, 0.06), rgba(13, 148, 136, 0.04)),
    #fff;
  padding: 16px;
}

.template-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.template-panel-head h3 {
  margin: 0 0 4px;
  font-size: 1rem;
}

.template-panel-head p {
  margin: 0;
}

.template-panel-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.template-panel-card {
  border: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
  border-radius: 10px;
  background: rgba(248, 250, 252, 0.78);
  padding: 12px 14px;
}

.template-panel-card h4 {
  margin: 0 0 8px;
  font-size: 0.88rem;
}

.template-flow-pre {
  margin: 0;
  padding: 0;
  background: transparent;
  color: var(--text-primary, #1a1d26);
  white-space: pre-wrap;
  font-family: ui-monospace, SFMono-Regular, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.8rem;
}

.badge-enabled {
  color: #0f766e;
  border-color: rgba(15, 118, 110, 0.18);
  background: rgba(15, 118, 110, 0.08);
}

.badge-disabled {
  color: #9a3412;
  border-color: rgba(154, 52, 18, 0.18);
  background: rgba(154, 52, 18, 0.08);
}

@media (max-width: 720px) {
  .template-panel-grid {
    grid-template-columns: 1fr;
  }
}
</style>
