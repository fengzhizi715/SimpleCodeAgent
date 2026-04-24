import { createRouter, createWebHistory } from "vue-router";
import OverviewPage from "./pages/OverviewPage.vue";
import RunPage from "./pages/RunPage.vue";
import HistoryPage from "./pages/HistoryPage.vue";
import RunExecutionPage from "./pages/RunExecutionPage.vue";
import RunTracePage from "./pages/RunTracePage.vue";
import RagPage from "./pages/RagPage.vue";
import AgentsPage from "./pages/AgentsPage.vue";

const routes = [
  { path: "/", redirect: "/overview" },
  { path: "/overview", name: "overview", component: OverviewPage, meta: { title: "系统概况" } },
  { path: "/run", name: "run", component: RunPage, meta: { title: "运行任务" } },
  { path: "/history", name: "history", component: HistoryPage, meta: { title: "运行历史" } },
  { path: "/agents", name: "agents", component: AgentsPage, meta: { title: "智能体列表" } },
  { path: "/rag", name: "rag", component: RagPage, meta: { title: "RAG 文档库" } },
  {
    path: "/runs/:runId",
    name: "execution",
    component: RunExecutionPage,
    props: true,
    meta: { title: "执行详情" },
  },
  {
    path: "/runs/:runId/trace",
    name: "trace",
    component: RunTracePage,
    props: true,
    meta: { title: "Trace 时间线" },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
