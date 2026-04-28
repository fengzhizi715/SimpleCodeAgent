<template>
  <section class="panel">
    <div class="rag-page-head">
      <div>
        <h2>RAG 文档库</h2>
        <p class="muted">
          展示当前可用的 RAG 列表；点击某个库可进入独立详情页进行上传、重建和删除操作。
        </p>
      </div>
      <RouterLink class="rag-create-cta" :to="{ name: 'rag-create' }">
        <span>新建知识库</span>
        <strong>+</strong>
      </RouterLink>
    </div>
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
            <div class="row table-actions">
              <button
                class="btn-secondary btn-sm"
                @click="selectRag(item.rag_id)"
              >
                查看详情
              </button>
              <button
                v-if="item.rag_id !== 'default'"
                class="btn-danger btn-sm"
                :disabled="deletingRagId === item.rag_id"
                @click="removeRagCollection(item)"
              >
                {{ deletingRagId === item.rag_id ? "删除中..." : "删除" }}
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">暂无 RAG 集合。</p>
    <p v-if="error" class="error" style="margin-top: 10px">{{ error }}</p>
  </section>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { useRouter } from "vue-router";
import { deleteRagCollection, listRagCollections } from "../api";

const router = useRouter();
const error = ref("");
const ragCollections = ref([{ rag_id: "default", collection_name: "codeagent_docs" }]);
const deletingRagId = ref("");

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

async function removeRagCollection(item) {
  const ragId = String(item?.rag_id || "").trim();
  if (!ragId || ragId === "default" || deletingRagId.value) return;
  const ok = window.confirm(`确认删除知识库「${ragId}」吗？该操作会删除该库的向量集合与切分配置。`);
  if (!ok) return;

  deletingRagId.value = ragId;
  error.value = "";
  try {
    await deleteRagCollection(ragId);
    await loadRagCollections();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "删除知识库失败";
  } finally {
    deletingRagId.value = "";
  }
}
</script>

<style scoped>
.rag-page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.rag-page-head h2 {
  margin-bottom: 8px;
}

.rag-page-head p {
  margin-top: 0;
}

.rag-create-cta {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  padding: 10px 14px;
  border: 1px solid rgba(14, 116, 144, 0.28);
  border-radius: 16px;
  background:
    linear-gradient(135deg, rgba(14, 116, 144, 0.12), rgba(79, 70, 229, 0.08)),
    #fff;
  color: #0f766e;
  text-decoration: none;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(15, 20, 25, 0.04));
}

.rag-create-cta:hover {
  border-color: rgba(14, 116, 144, 0.44);
  color: #0f766e;
  text-decoration: none;
}

.rag-create-cta strong {
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  border-radius: 999px;
  background: #0f766e;
  color: #fff;
  font-size: 1rem;
  line-height: 1;
}

.mono {
  font-family: var(--font-mono);
  font-size: 0.8125rem;
  word-break: break-all;
}

.table-actions {
  gap: 8px;
}

@media (max-width: 720px) {
  .rag-page-head {
    flex-direction: column;
  }

  .rag-create-cta {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
