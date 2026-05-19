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


def test_v3_execution_page_composes_task_aware_primary_answer() -> None:
    page = Path("webui/src/pages/RunExecutionPage.vue").read_text(encoding="utf-8")

    assert "composeV3AnalysisAnswer" in page
    assert "composeV3CodingAnswer" in page
    assert "composeV3TestingAnswer" in page
    assert "v3PrimaryAnswer" in page


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
