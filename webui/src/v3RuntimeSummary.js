export function normalizeV3RuntimeSummary(value) {
  if (!value || typeof value !== "object") {
    return {
      run_mode: null,
      flow_cards: [],
      governance_summary: { status_counts: {}, items: [] },
      recovery_summary: {
        status: "not_triggered",
        label: "No Recovery Triggered",
        trigger_skill_name: null,
        parent_node_id: null,
        patch_summary: "",
        verification_summary: "",
        stop_reason: null,
        recovered_node_ids: [],
      },
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
    recovery_summary: value.recovery_summary && typeof value.recovery_summary === "object"
      ? {
          status: value.recovery_summary.status || "not_triggered",
          label: value.recovery_summary.label || "No Recovery Triggered",
          trigger_skill_name: value.recovery_summary.trigger_skill_name || null,
          parent_node_id: value.recovery_summary.parent_node_id || null,
          patch_summary: value.recovery_summary.patch_summary || "",
          verification_summary: value.recovery_summary.verification_summary || "",
          stop_reason: value.recovery_summary.stop_reason || null,
          recovered_node_ids: Array.isArray(value.recovery_summary.recovered_node_ids)
            ? value.recovery_summary.recovered_node_ids
            : [],
        }
      : {
          status: "not_triggered",
          label: "No Recovery Triggered",
          trigger_skill_name: null,
          parent_node_id: null,
          patch_summary: "",
          verification_summary: "",
          stop_reason: null,
          recovered_node_ids: [],
        },
    demo_scenarios: Array.isArray(value.demo_scenarios) ? value.demo_scenarios : [],
  };
}

export function formatGovernanceCount(statusCounts, key) {
  if (!statusCounts || typeof statusCounts !== "object") {
    return "0";
  }
  return String(statusCounts[key] || 0);
}
