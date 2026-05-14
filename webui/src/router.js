import { createRouter, createWebHistory } from "vue-router";
import OverviewPage from "./pages/OverviewPage.vue";
import DashboardPage from "./pages/DashboardPage.vue";
import RunPage from "./pages/RunPage.vue";
import HistoryPage from "./pages/HistoryPage.vue";
import RunExecutionPage from "./pages/RunExecutionPage.vue";
import RunTracePage from "./pages/RunTracePage.vue";
import RagPage from "./pages/RagPage.vue";
import RagCreatePage from "./pages/RagCreatePage.vue";
import RagDetailPage from "./pages/RagDetailPage.vue";
import AgentsPage from "./pages/AgentsPage.vue";

const routes = [
  { path: "/", redirect: "/overview" },
  { path: "/overview", name: "overview", component: OverviewPage, meta: { title: "系统概况" } },
  { path: "/dashboard", name: "dashboard", component: DashboardPage, meta: { title: "Token Dashboard" } },
  { path: "/run", name: "run", component: RunPage, meta: { title: "运行任务" } },
  { path: "/history", name: "history", component: HistoryPage, meta: { title: "运行历史" } },
  { path: "/agents", name: "agents", component: AgentsPage, meta: { title: "能力目录" } },
  { path: "/rag", name: "rag", component: RagPage, meta: { title: "RAG 文档库" } },
  {
    path: "/rag/new",
    name: "rag-create",
    component: RagCreatePage,
    meta: { title: "新建知识库", showBack: true },
  },
  {
    path: "/rag/:ragId",
    name: "rag-detail",
    component: RagDetailPage,
    props: true,
    meta: { title: "RAG 详情", showBack: true },
  },
  {
    path: "/runs/:runId",
    name: "execution",
    component: RunExecutionPage,
    props: true,
    meta: { title: "执行详情", showBack: true },
  },
  {
    path: "/runs/:runId/trace",
    name: "trace",
    component: RunTracePage,
    props: true,
    meta: { title: "Trace 时间线", showBack: true },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
