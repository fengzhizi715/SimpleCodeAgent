<template>
  <section class="panel">
    <h2>RAG 文档库</h2>
    <p class="muted">
      展示当前可用的 RAG 列表；点击某个库可进入独立详情页进行上传、重建和删除操作。
    </p>
    <h3 style="margin-top: 14px">RAG 列表</h3>
    <table v-if="ragCollections.length">
      <thead>
        <tr>
          <th>rag_id</th>
          <th>collection</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="item in ragCollections"
          :key="item.rag_id"
        >
          <td class="mono">{{ item.rag_id }}</td>
          <td class="mono">{{ item.collection_name }}</td>
          <td>
            <button
              class="btn-secondary btn-sm"
              @click="selectRag(item.rag_id)"
            >
              查看详情
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">暂无 RAG 集合。</p>
    <p v-if="error" class="error" style="margin-top: 10px">{{ error }}</p>
    <div class="row rag-create-row" style="margin-top: 12px; flex-wrap: wrap">
      <label style="margin-bottom: 0">新建知识库</label>
      <input
        v-model="newRagId"
        class="rag-create-input"
        placeholder="例如 product-docs、backend_java"
        style="max-width: 280px"
        @keydown.enter.prevent="submitCreateRag"
      />
      <button class="btn-primary" :disabled="creating || !newRagIdTrimmed" @click="submitCreateRag">
        {{ creating ? "创建中..." : "创建空库" }}
      </button>
      <span class="muted rag-create-hint">名称会规范为小写；与 default 重复或仅含符号将被拒绝。创建后可在 Run 页（v2）选择。</span>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { createRagCollection, listRagCollections } from "../api";

const router = useRouter();
const error = ref("");
const ragCollections = ref([{ rag_id: "default", collection_name: "codeagent_docs" }]);
const newRagId = ref("");
const creating = ref(false);
const uploadMessage = ref("");
const newRagIdTrimmed = computed(() => String(newRagId.value ?? "").trim());

onMounted(async () => {
  await loadRagCollections();
});

async function loadRagCollections() {
  try {
    const data = await listRagCollections();
    const items = Array.isArray(data?.items) ? data.items : [];
    if (items.length) {
      ragCollections.value = items;
      return;
    }
  } catch {
    // noop: fallback below
  }
  ragCollections.value = [{ rag_id: "default", collection_name: "codeagent_docs" }];
}

async function selectRag(nextRagId) {
  const value = String(nextRagId || "").trim();
  if (!value) return;
  await router.push({ name: "rag-detail", params: { ragId: value } });
}

async function submitCreateRag() {
  const id = newRagIdTrimmed.value;
  if (!id || creating.value) return;
  creating.value = true;
  error.value = "";
  uploadMessage.value = "";
  try {
    const result = await createRagCollection(id);
    const resolved = result?.rag_id ? String(result.rag_id) : id;
    uploadMessage.value = `已创建知识库：${resolved}（collection: ${result?.collection_name || ""}）`;
    newRagId.value = "";
    await loadRagCollections();
    await router.push({ name: "rag-detail", params: { ragId: resolved } });
  } catch (err) {
    error.value = err instanceof Error ? err.message : "创建失败";
  } finally {
    creating.value = false;
  }
}
</script>

<style scoped>
.mono {
  font-family: var(--font-mono);
  font-size: 0.8125rem;
  word-break: break-all;
}

.table-actions {
  gap: 8px;
}

.rag-create-row {
  align-items: center;
  gap: 10px;
}

.rag-create-hint {
  flex: 1 1 220px;
  font-size: 0.8125rem;
  line-height: 1.4;
}

@media (max-width: 720px) {
  .rag-create-input {
    width: 100%;
    max-width: none !important;
  }
}
</style>
