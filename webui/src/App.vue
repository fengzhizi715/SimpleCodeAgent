<template>
  <div class="app-shell">
    <header class="app-header">
      <h1>SimpleCodeAgent V2 UI MVP</h1>
      <nav class="app-nav">
        <RouterLink to="/">Run</RouterLink>
        <RouterLink to="/history">历史</RouterLink>
      </nav>
    </header>
    <main class="app-main">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { RouterLink, RouterView } from "vue-router";
</script>
