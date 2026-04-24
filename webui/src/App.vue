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
        <RouterLink to="/rag" class="side-nav-link" active-class="is-active">
          RAG
        </RouterLink>
      </nav>
    </aside>
    <div class="app-content">
      <header class="app-header">
        <h2>{{ pageTitle }}</h2>
      </header>
      <main class="app-main">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";

const route = useRoute();
const pageTitle = computed(() => {
  const t = route.meta?.title;
  return typeof t === "string" && t.length > 0 ? t : "控制台";
});
</script>
