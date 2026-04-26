<template>
  <section class="panel">
    <h2>RAG 详情</h2>
    <p class="muted">
      当前知识库：<span class="mono">{{ ragId }}</span>
    </p>
    <div class="row" style="margin-top: 10px">
      <button class="btn-secondary" :disabled="loading" @click="loadOverview">
        {{ loading ? "加载中..." : "刷新详情" }}
      </button>
      <span v-if="error" class="error">{{ error }}</span>
    </div>
  </section>

  <section class="panel">
    <h3>上传并导入文件</h3>
    <div class="grid-two">
      <div>
        <label>目标目录（docs 下）</label>
        <input v-model="uploadDir" placeholder="例如 uploads 或 rag/project-a" />
      </div>
      <div>
        <label>选择文件</label>
        <input ref="fileInputRef" type="file" @change="onFileChange" />
      </div>
    </div>
    <div class="row" style="margin-top: 12px">
      <button class="btn-primary" :disabled="uploading || !selectedFile" @click="submitUpload">
        {{ uploading ? "上传中..." : "上传并导入" }}
      </button>
      <span v-if="uploadMessage" class="muted">{{ uploadMessage }}</span>
    </div>
  </section>

  <section class="panel" v-if="overview">
    <h3>向量库概览</h3>
    <table>
      <tbody>
        <tr><th>backend</th><td>{{ overview.backend }}</td></tr>
        <tr><th>rag_id</th><td>{{ overview.rag_id }}</td></tr>
        <tr><th>collection</th><td>{{ overview.collection_name }}</td></tr>
        <tr><th>persist_dir</th><td class="mono">{{ overview.persist_dir }}</td></tr>
        <tr><th>total_chunks</th><td>{{ overview.total_chunks }}</td></tr>
        <tr><th>file_count</th><td>{{ overview.file_count }}</td></tr>
      </tbody>
    </table>
  </section>

  <section class="panel" v-if="overview">
    <h3>Embedding 配置</h3>
    <table>
      <tbody>
        <tr><th>provider</th><td>{{ overview.embedding_provider }}</td></tr>
        <tr><th>model</th><td>{{ overview.embedding_model }}</td></tr>
        <tr><th>base_url</th><td class="mono">{{ overview.embedding_base_url }}</td></tr>
      </tbody>
    </table>
  </section>

  <section class="panel" v-if="overview">
    <h3>已入库文件</h3>
    <table v-if="overview.files.length">
      <thead>
        <tr>
          <th>source</th>
          <th>chunks</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in topFiles" :key="item.source">
          <td class="mono">{{ item.source }}</td>
          <td>{{ item.chunk_count }}</td>
          <td>
            <div class="row table-actions">
              <button
                class="btn-secondary btn-sm"
                :disabled="reindexingSource === item.source"
                @click="reindexSource(item)"
              >
                {{ reindexingSource === item.source ? "重建中..." : "重建索引" }}
              </button>
              <button class="btn-danger btn-sm" :disabled="deletingSource === item.source" @click="removeSource(item)">
                {{ deletingSource === item.source ? "删除中..." : "删除" }}
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="overview.file_count > 0" class="row" style="margin-top: 12px; justify-content: space-between">
      <div class="row">
        <label style="margin-bottom: 0">每页</label>
        <select v-model.number="pageSize" @change="onPageSizeChange">
          <option :value="10">10</option>
          <option :value="20">20</option>
          <option :value="50">50</option>
        </select>
      </div>
      <div class="row">
        <span class="muted">第 {{ currentPage }} / {{ totalPages }} 页，共 {{ overview.file_count }} 个文件</span>
        <button class="btn-secondary" :disabled="currentPage <= 1 || loading" @click="goPrevPage">上一页</button>
        <button class="btn-secondary" :disabled="currentPage >= totalPages || loading" @click="goNextPage">
          下一页
        </button>
      </div>
    </div>
    <p v-else class="muted">当前向量库暂无文件数据，请先执行文档导入。</p>
  </section>

  <section class="panel" v-if="!overview && !loading && !error">
    <p class="muted">当前 RAG 暂无数据。</p>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { deleteRagSource, getRagOverview, listRagCollections, reindexRagSource, uploadRagFile } from "../api";

const route = useRoute();
const router = useRouter();
const overview = ref(null);
const loading = ref(false);
const error = ref("");
const deletingSource = ref("");
const reindexingSource = ref("");
const pageSize = ref(20);
const page = ref(1);
const selectedFile = ref(null);
const uploadDir = ref("uploads");
const uploadMessage = ref("");
const fileInputRef = ref(null);
const uploading = ref(false);
const ragCollections = ref([]);

const ragId = computed(() => String(route.params.ragId || "").trim());
const topFiles = computed(() => (Array.isArray(overview.value?.files) ? overview.value.files : []));
const totalPages = computed(() => {
  const total = Number(overview.value?.file_count || 0);
  return Math.max(1, Math.ceil(total / pageSize.value));
});
const currentPage = computed(() => page.value);

async function loadCollectionsAndGuard() {
  try {
    const data = await listRagCollections();
    const items = Array.isArray(data?.items) ? data.items : [];
    ragCollections.value = items;
    if (items.length > 0 && !items.some((item) => item.rag_id === ragId.value)) {
      router.replace({ name: "rag" });
    }
  } catch {
    // ignore
  }
}

async function loadOverview() {
  loading.value = true;
  error.value = "";
  try {
    const data = await getRagOverview({
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
      ragId: ragId.value || "default",
    });
    overview.value = data && typeof data === "object" ? data : null;
    const pages = Math.max(1, Math.ceil(Number(overview.value?.file_count || 0) / pageSize.value));
    if (page.value > pages) {
      page.value = pages;
      await loadOverview();
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载 RAG 数据失败";
    overview.value = null;
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  await loadCollectionsAndGuard();
  if (ragId.value) {
    await loadOverview();
  }
});

async function goPrevPage() {
  if (page.value <= 1) return;
  page.value -= 1;
  await loadOverview();
}

async function goNextPage() {
  if (page.value >= totalPages.value) return;
  page.value += 1;
  await loadOverview();
}

async function onPageSizeChange() {
  page.value = 1;
  await loadOverview();
}

function onFileChange(event) {
  const input = event?.target;
  const file = input?.files && input.files[0] ? input.files[0] : null;
  selectedFile.value = file;
}

async function submitUpload() {
  if (!selectedFile.value) return;
  uploading.value = true;
  uploadMessage.value = "";
  error.value = "";
  try {
    const result = await uploadRagFile(
      selectedFile.value,
      uploadDir.value || "uploads",
      ragId.value || "default",
    );
    uploadMessage.value = `已导入 ${result.source}（rag: ${result.rag_id}），新增 chunks: ${result.ingested_chunks}`;
    selectedFile.value = null;
    if (fileInputRef.value) {
      fileInputRef.value.value = "";
    }
    await loadOverview();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "上传导入失败";
  } finally {
    uploading.value = false;
  }
}

async function removeSource(item) {
  const source = item?.source || "";
  const chunkCount = Number(item?.chunk_count || 0);
  if (!source) return;
  const ok = window.confirm(
    `确认删除 "${source}" 的所有向量分块吗？\n预计删除 chunks: ${chunkCount}`,
  );
  if (!ok) return;

  deletingSource.value = source;
  error.value = "";
  uploadMessage.value = "";
  try {
    const result = await deleteRagSource(source, ragId.value || "default");
    uploadMessage.value = `已删除 ${result.source}（rag: ${result.rag_id}），删除 chunks: ${result.deleted_chunks}`;
    await loadOverview();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "删除失败";
  } finally {
    deletingSource.value = "";
  }
}

async function reindexSource(item) {
  const source = item?.source || "";
  const chunkCount = Number(item?.chunk_count || 0);
  if (!source) return;
  const ok = window.confirm(
    `确认重建 "${source}" 的索引吗？\n当前已入库 chunks: ${chunkCount}\n将先删除旧索引再重建。`,
  );
  if (!ok) return;

  reindexingSource.value = source;
  error.value = "";
  uploadMessage.value = "";
  try {
    const result = await reindexRagSource(source, ragId.value || "default");
    uploadMessage.value = `已重建 ${result.source}（rag: ${result.rag_id}），删除 chunks: ${result.deleted_chunks}，新建 chunks: ${result.ingested_chunks}`;
    await loadOverview();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "重建索引失败";
  } finally {
    reindexingSource.value = "";
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
</style>
