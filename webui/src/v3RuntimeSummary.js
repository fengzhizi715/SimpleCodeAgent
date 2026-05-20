export function normalizeV3RuntimeSummary(value) {
  if (!value || typeof value !== "object") {
    return {
      run_mode: null,
      flow_cards: [],
      governance_summary: { status_counts: {}, items: [] },
      demo_scenarios: [],
    };
  }
  return {
    run_mode: value.run_mode && typeof value.run_mode === "object" ? value.run_mode : null,
    flow_cards: Array.isArray(value.flow_cards) ? value.flow_cards : [],
    governance_summary: value.governance_summary && typeof value.governance_summary === "object"
      ? {
          status_counts: value.governance_summary.status_counts || {},
          items: Array.isArray(value.governance_summary.items) ? value.governance_summary.items : [],
        }
      : { status_counts: {}, items: [] },
    demo_scenarios: Array.isArray(value.demo_scenarios) ? value.demo_scenarios : [],
  };
}

export function formatGovernanceCount(statusCounts, key) {
  if (!statusCounts || typeof statusCounts !== "object") {
    return "0";
  }
  return String(statusCounts[key] || 0);
}
