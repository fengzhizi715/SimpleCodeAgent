from pathlib import Path


def test_webui_vite_proxy_includes_run_endpoint() -> None:
    vite_config = Path("webui/vite.config.js").read_text(encoding="utf-8")

    assert '"/run"' in vite_config


def test_v3_trace_page_uses_run_detail_metadata() -> None:
    page = Path("webui/src/pages/RunTracePage.vue").read_text(encoding="utf-8")

    assert "getRunDetail" in page
    assert '["v2", "v3"].includes(normalizedVersion)' in page


def test_v3_execution_page_surfaces_final_summary() -> None:
    page = Path("webui/src/pages/RunExecutionPage.vue").read_text(encoding="utf-8")

    assert "v3FinalSummary" in page
    assert "v3-summary-card" in page


def test_v3_execution_page_uses_result_first_layout() -> None:
    page = Path("webui/src/pages/RunExecutionPage.vue").read_text(encoding="utf-8")

    assert "v3PrimaryAnswer" in page
    assert "v3KeyFindings" in page
    assert "v3OverviewCards" in page
    assert "v3-flow-detail" in page


def test_v3_execution_page_surfaces_outcome_next_step_and_risks() -> None:
    page = Path("webui/src/pages/RunExecutionPage.vue").read_text(encoding="utf-8")

    assert "v3OutcomeCards" in page
    assert "Outcome" in page
    assert "Next Step" in page
    assert "Risks" in page


def test_v3_execution_page_surfaces_runtime_mode_flow_cards_and_governance_explain() -> None:
    page = Path("webui/src/pages/RunExecutionPage.vue").read_text(encoding="utf-8")

    assert "v3RuntimeSummary" in page
    assert "v3RunModeCard" in page
    assert "v3FlowCards" in page
    assert "v3GovernanceExplainItems" in page
    assert "Runtime Mode" in page
    assert "Flow Cards" in page
    assert "Governance Explain" in page
    assert "v3RecoverySummary" in page
    assert "Recovery Path" in page


def test_v3_execution_page_composes_task_aware_primary_answer() -> None:
    page = Path("webui/src/pages/RunExecutionPage.vue").read_text(encoding="utf-8")

    assert "composeV3AnalysisAnswer" in page
    assert "composeV3CodingAnswer" in page
    assert "composeV3TestingAnswer" in page
    assert "v3PrimaryAnswer" in page


def test_v3_analysis_answer_prioritizes_chinese_summary() -> None:
    page = Path("webui/src/pages/RunExecutionPage.vue").read_text(encoding="utf-8")

    assert "中文结果摘要" in page
    assert "原始详细分析（模型输出）" in page


def test_history_page_supports_bulk_delete_controls() -> None:
    page = Path("webui/src/pages/HistoryPage.vue").read_text(encoding="utf-8")

    assert "selectedRunIds" in page
    assert "removeSelectedRuns" in page
    assert "toggleSelectAllVisible" in page
    assert "history-actions-sticky" in page


def test_run_page_exposes_v3_planning_mode() -> None:
    page = Path("webui/src/pages/RunPage.vue").read_text(encoding="utf-8")

    assert "v3_planning_mode" in page
    assert 'payload.v3_planning_mode = form.v3_planning_mode' in page
    assert "runV3RecoveryDemo" in page
    assert "Recovery Demo" in page


def test_router_registers_autonomy_page() -> None:
    router = Path("webui/src/router.js").read_text(encoding="utf-8")

    assert 'name: "autonomy"' in router
    assert 'path: "/autonomy"' in router


def test_sidebar_exposes_autonomy_entry() -> None:
    app_shell = Path("webui/src/App.vue").read_text(encoding="utf-8")

    assert 'to="/autonomy"' in app_shell
    assert "Autonomy" in app_shell


def test_autonomy_page_includes_graph_events_and_triggers_tabs() -> None:
    page = Path("webui/src/pages/AutonomyPage.vue").read_text(encoding="utf-8")

    assert "Overview" in page
    assert "Graph" in page
    assert "Events" in page
    assert "Triggers" in page
    assert "getV3EventChain" in page
    assert "listRuns" in page


def test_autonomy_page_surfaces_runtime_status_and_demo_scenarios() -> None:
    page = Path("webui/src/pages/AutonomyPage.vue").read_text(encoding="utf-8")

    assert "runtimeSummary" in page
    assert "runtimeStatusCards" in page
    assert "recoveryStatusCards" in page
    assert "flowCards" in page
    assert "governanceExplainItems" in page
    assert "demoScenarios" in page
    assert "demoCatalog" in page
    assert "Runtime Status" in page
    assert "Recovery Demos" in page
    assert "Replay Compare" in page


def test_autonomy_page_can_launch_recovery_demos_and_open_replay_compare() -> None:
    page = Path("webui/src/pages/AutonomyPage.vue").read_text(encoding="utf-8")

    assert "launchRecoveryDemo" in page
    assert "openReplayCompare" in page
    assert "runV3RecoveryDemo" in page
    assert "getV3RunReplayPlan" in page
    assert "replayV3EventChain" in page
    assert "recentDemoRunsByScenario" in page


def test_autonomy_page_reads_url_filters() -> None:
    page = Path("webui/src/pages/AutonomyPage.vue").read_text(encoding="utf-8")

    assert "route.query.run_id" in page
    assert "route.query.event_type" in page
    assert "route.query.trigger_rule" in page


def test_autonomy_page_writes_url_filters_back_to_router() -> None:
    page = Path("webui/src/pages/AutonomyPage.vue").read_text(encoding="utf-8")

    assert "event_type: selectedEventType.value || undefined" in page
    assert "trigger_rule: selectedTriggerRule.value || undefined" in page
    assert "run_id: selectedRunId.value || undefined" in page


def test_autonomy_page_filters_events_and_trigger_rules() -> None:
    page = Path("webui/src/pages/AutonomyPage.vue").read_text(encoding="utf-8")

    assert "filteredEventRows" in page
    assert "filteredTriggerRules" in page
    assert "selectedEventType" in page
    assert "selectedTriggerRule" in page


def test_autonomy_page_only_opens_event_chain_for_inspectable_events() -> None:
    page = Path("webui/src/pages/AutonomyPage.vue").read_text(encoding="utf-8")

    assert "canInspectEventChain" in page
    assert "无法展开 event chain" in page
    assert ":disabled=\"!canInspectEventChain(item)\"" in page
