<template>
  <div class="app-shell">
    <aside class="app-sidebar">
      <div class="app-brand">
        <h1>SimpleCodeAgent</h1>
      </div>
      <nav class="side-nav">
        <RouterLink to="/overview" class="side-nav-link" active-class="is-active">
          系统概况
        </RouterLink>
        <RouterLink to="/run" class="side-nav-link" active-class="is-active">
          运行任务
        </RouterLink>
        <RouterLink to="/history" class="side-nav-link" active-class="is-active">
          历史记录
        </RouterLink>
        <RouterLink to="/agents" class="side-nav-link" active-class="is-active">
          智能体列表
        </RouterLink>
        <RouterLink to="/rag" class="side-nav-link" active-class="is-active">
          RAG
        </RouterLink>
      </nav>
    </aside>
    <div class="app-content">
      <header class="app-header">
        <div class="app-header-main">
          <button
            v-if="showHeaderBack"
            type="button"
            class="header-back-btn"
            aria-label="返回上一页"
            title="返回"
            @click="goBack"
          >
            ←
          </button>
          <h2>{{ pageTitle }}</h2>
        </div>
      </header>
      <main class="app-main">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";

const route = useRoute();
const router = useRouter();
const pageTitle = computed(() => {
  const t = route.meta?.title;
  return typeof t === "string" && t.length > 0 ? t : "控制台";
});
const showHeaderBack = computed(() => {
  return Boolean(route.meta?.showBack);
});

function goBack() {
  if (window.history.length > 1) {
    router.back();
    return;
  }
  router.push({ name: "history" });
}
</script>

<style scoped>
.app-header-main {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-back-btn {
  width: 30px;
  height: 30px;
  border-radius: 999px;
  border: 1px solid var(--border-strong, rgba(15, 20, 25, 0.12));
  background: #fff;
  color: var(--text-primary, #1a1d26);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
}

.header-back-btn:hover {
  background: #f5f6fa;
}
</style>
