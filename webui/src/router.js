import { createRouter, createWebHistory } from "vue-router";
import RunPage from "./pages/RunPage.vue";
import HistoryPage from "./pages/HistoryPage.vue";
import RunExecutionPage from "./pages/RunExecutionPage.vue";
import RunTracePage from "./pages/RunTracePage.vue";

const routes = [
  { path: "/", name: "run", component: RunPage },
  { path: "/history", name: "history", component: HistoryPage },
  { path: "/runs/:runId", name: "execution", component: RunExecutionPage, props: true },
  { path: "/runs/:runId/trace", name: "trace", component: RunTracePage, props: true },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
