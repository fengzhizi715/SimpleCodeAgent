<template>
  <section class="panel rag-create-panel">
    <div class="rag-create-head">
      <div>
        <h2>新建知识库</h2>
        <p class="muted">
          创建一个空的 RAG 文档库。创建成功后会自动跳转到详情页，你可以继续上传文档、重建索引或在 V2 运行中选择它。
        </p>
      </div>
    </div>

    <div class="rag-create-form">
      <label>知识库 ID</label>
      <input
        v-model="newRagId"
        placeholder="例如 product-docs、backend_java"
        @keydown.enter.prevent="submitCreateRag"
      />
      <p class="muted">
        名称会规范为小写；与 default 重复或仅含符号将被拒绝。建议使用和项目或课程主题相关的名称。
      </p>

      <div class="rag-create-preview">
        <span>将创建为</span>
        <code>{{ newRagIdTrimmed || "—" }}</code>
      </div>

      <div class="rag-advanced-card">
        <div class="rag-advanced-head">
          <div>
            <strong>高级配置</strong>
            <p class="muted">创建后上传和重建索引会使用这里的切分参数；Embedding 仍使用系统默认配置。</p>
          </div>
          <span class="rag-coming-soon">MVP</span>
        </div>

        <div class="rag-advanced-grid">
          <div>
            <label>Chunk Size</label>
            <input v-model.number="advanced.chunkSize" type="number" min="100" max="8000" step="50" />
            <p class="muted">单个文本块的最大字符数，默认 800。</p>
          </div>
          <div>
            <label>Overlap</label>
            <input v-model.number="advanced.overlap" type="number" min="0" max="4000" step="10" />
            <p class="muted">相邻 chunk 的重叠字符数，必须小于 Chunk Size。</p>
          </div>
          <div>
            <label>Embedding Provider</label>
            <select v-model="advanced.embeddingProvider" disabled>
              <option value="system">使用系统默认</option>
            </select>
            <p class="muted">当前暂不支持按知识库覆盖。</p>
          </div>
          <div>
            <label>Embedding Model</label>
            <input v-model="advanced.embeddingModel" disabled />
            <p class="muted">后续可扩展为每个知识库独立选择。</p>
          </div>
        </div>
      </div>

      <p v-if="error" class="error">{{ error }}</p>

      <div class="rag-create-actions">
        <button class="btn-primary" :disabled="creating || !newRagIdTrimmed" @click="submitCreateRag">
          {{ creating ? "创建中..." : "创建知识库" }}
        </button>
        <RouterLink class="rag-cancel-link" :to="{ name: 'rag' }">
          取消并返回列表
        </RouterLink>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { createRagCollection } from "../api";

const router = useRouter();
const newRagId = ref("");
const creating = ref(false);
const error = ref("");
const newRagIdTrimmed = computed(() => String(newRagId.value ?? "").trim());
const advanced = ref({
  chunkSize: "800",
  overlap: "120",
  embeddingProvider: "system",
  embeddingModel: "系统默认",
});

async function submitCreateRag() {
  const id = newRagIdTrimmed.value;
  if (!id || creating.value) return;
  creating.value = true;
  error.value = "";
  try {
    if (advanced.value.overlap >= advanced.value.chunkSize) {
      error.value = "Overlap 必须小于 Chunk Size。";
      return;
    }
    const result = await createRagCollection(id, {
      chunk_size: advanced.value.chunkSize,
      overlap: advanced.value.overlap,
    });
    const resolved = result?.rag_id ? String(result.rag_id) : id;
    await router.push({ name: "rag-detail", params: { ragId: resolved } });
  } catch (err) {
    error.value = err instanceof Error ? err.message : "创建失败";
  } finally {
    creating.value = false;
  }
}
</script>

<style scoped>
.rag-create-panel {
  max-width: 760px;
}

.rag-create-head {
  max-width: 680px;
}

.rag-create-head h2 {
  margin-bottom: 8px;
}

.rag-create-head p {
  margin-top: 0;
}

.rag-create-form {
  margin-top: 18px;
  padding: 18px;
  border: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
  border-radius: 18px;
  background: #f8fafc;
}

.rag-create-form input {
  margin-bottom: 8px;
}

.rag-create-preview {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  padding: 12px;
  border: 1px dashed rgba(14, 116, 144, 0.28);
  border-radius: 14px;
  background: #fff;
}

.rag-create-preview span {
  color: var(--text-muted, #8b929e);
  font-size: 0.82rem;
  font-weight: 700;
}

.rag-create-preview code {
  font-family: var(--font-mono);
}

.rag-advanced-card {
  margin-top: 16px;
  padding: 16px;
  border: 1px solid rgba(100, 116, 139, 0.16);
  border-radius: 18px;
  background:
    linear-gradient(135deg, rgba(100, 116, 139, 0.08), transparent 48%),
    #fff;
}

.rag-advanced-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.rag-advanced-head strong {
  display: block;
  font-size: 0.95rem;
}

.rag-advanced-head p {
  margin: 3px 0 0;
}

.rag-coming-soon {
  flex-shrink: 0;
  border-radius: 999px;
  padding: 4px 9px;
  background: #f1f5f9;
  color: #64748b;
  font-size: 0.75rem;
  font-weight: 800;
}

.rag-advanced-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.rag-advanced-grid input,
.rag-advanced-grid select {
  margin-bottom: 6px;
}

.rag-advanced-grid .muted {
  margin: 0;
  font-size: 0.78rem;
  line-height: 1.4;
}

.rag-create-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
}

.rag-cancel-link {
  display: inline-flex;
  align-items: center;
  min-height: 40px;
  padding: 0 2px;
  color: var(--text-secondary, #5c6370);
  font-weight: 700;
}

.rag-cancel-link:hover {
  color: var(--accent-text, #4338ca);
}

@media (max-width: 720px) {
  .rag-advanced-grid {
    grid-template-columns: 1fr;
  }
}
</style>
