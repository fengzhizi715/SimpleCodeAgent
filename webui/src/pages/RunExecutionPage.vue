<template>
  <section class="panel">
    <h2>Run Execution</h2>
    <div class="row">
      <span class="badge">run_id: {{ runId }}</span>
      <span v-if="detailVersion" class="badge">{{ detailVersion.toUpperCase() }}</span>
      <button class="btn-secondary" @click="fetchReplay">手动刷新</button>
      <button class="btn-secondary" @click="goTrace">查看 Trace</button>
    </div>
    <p class="muted" style="margin-top: 8px">
      {{
        isV3Detail
          ? "当前展示 v3 面向 graph runtime 的图执行节点能力详情视图。"
          : `轮询状态：${polling ? "开启" : "关闭"}`
      }}
    </p>
    <p v-if="error" class="error">{{ error }}</p>
  </section>

  <template v-if="isV3Detail">
    <section class="panel" v-if="replay.run">
      <div class="v3-result-hero">
        <div class="v3-run-header">
          <div class="v3-run-title">
            <h3>{{ replay.run.task || "未命名任务" }}</h3>
            <div class="v3-run-badges">
              <span class="badge">{{ detailVersion.toUpperCase() }}</span>
              <span class="status-badge" :class="statusBadgeClass(replay.run.status)">{{ replay.run.status }}</span>
            </div>
          </div>
          <div class="v3-run-meta">
            <span class="v3-meta-item"><strong>Model:</strong> {{ replay.run.model || "—" }}</span>
            <span class="v3-meta-item"><strong>Tokens:</strong> {{ formatTokens(replay.run) }}</span>
            <span class="v3-meta-item"><strong>Workdir:</strong> {{ replay.run.workdir || "—" }}</span>
          </div>
        </div>

        <div class="v3-overview-grid">
          <article v-for="card in v3OverviewCards" :key="card.label" class="v3-overview-card">
            <span>{{ card.label }}</span>
            <strong>{{ card.value }}</strong>
            <small v-if="card.help">{{ card.help }}</small>
          </article>
        </div>
      </div>
    </section>

    <section class="panel" v-if="v3RuntimeSummary.run_mode">
      <div class="v3-section-head">
        <div>
          <h3>Runtime Mode</h3>
          <p class="muted">先明确本次 v3 到底只是 graph，还是已经进入 trigger、autonomy 或 governance 路径。</p>
        </div>
      </div>
      <div class="v3-key-findings">
        <article class="v3-key-card">
          <span>Mode</span>
          <strong>{{ v3RunModeCard.value }}</strong>
          <small>{{ v3RunModeCard.help }}</small>
        </article>
        <article class="v3-key-card">
          <span>Allowed</span>
          <strong>{{ formatGovernanceCount(v3RuntimeSummary.governance_summary.status_counts, "allowed") }}</strong>
          <small>已进入 follow-up</small>
        </article>
        <article class="v3-key-card">
          <span>Blocked</span>
          <strong>{{ formatGovernanceCount(v3RuntimeSummary.governance_summary.status_counts, "blocked") }}</strong>
          <small>被 governance 拦截</small>
        </article>
        <article class="v3-key-card">
          <span>Cooled Down</span>
          <strong>{{ formatGovernanceCount(v3RuntimeSummary.governance_summary.status_counts, "cooled_down") }}</strong>
          <small>进入 cooldown</small>
        </article>
      </div>
      <div v-if="v3RuntimeSummary.demo_scenarios.length" class="autonomy-highlight-list" style="margin-top: 14px">
        <span v-for="item in v3RuntimeSummary.demo_scenarios" :key="item" class="badge">{{ item }}</span>
      </div>
    </section>

    <section class="panel" v-if="v3RecoverySummary.status !== 'not_triggered'">
      <div class="v3-section-head">
        <div>
          <h3>Recovery Path</h3>
          <p class="muted">把 test failure 之后是否真的进入补救、是否补救成功，直接翻译成第一屏能读懂的结果。</p>
        </div>
      </div>
      <div class="v3-key-findings">
        <article class="v3-key-card">
          <span>Status</span>
          <strong>{{ v3RecoverySummary.label }}</strong>
          <small>{{ v3RecoverySummary.trigger_skill_name ? `skill: ${v3RecoverySummary.trigger_skill_name}` : "未记录触发 skill" }}</small>
        </article>
        <article class="v3-key-card">
          <span>Patch</span>
          <strong>{{ v3RecoverySummary.patch_summary || "No patch summary" }}</strong>
          <small>{{ v3RecoverySummary.parent_node_id ? `parent: ${v3RecoverySummary.parent_node_id}` : "未记录 parent node" }}</small>
        </article>
        <article class="v3-key-card">
          <span>Verification</span>
          <strong>{{ v3RecoverySummary.verification_summary || "No verification summary" }}</strong>
          <small>{{ v3RecoverySummary.recovered_node_ids.length ? `recovered: ${v3RecoverySummary.recovered_node_ids.join(", ")}` : (v3RecoverySummary.stop_reason || "尚未记录 recovered node") }}</small>
        </article>
      </div>
    </section>

    <section class="panel">
      <div class="v3-primary-answer-head">
        <div>
          <h3>最终答案</h3>
          <p class="muted">先看本次运行最后产出了什么，再往下看它是怎么完成的。</p>
        </div>
      </div>
      <div class="v3-final-answer v3-final-answer-prominent" v-html="renderMarkdown(v3PrimaryAnswer)"></div>
      <div v-if="v3OutcomeCards.length" class="v3-outcome-grid">
        <article v-for="card in v3OutcomeCards" :key="card.label" class="v3-outcome-card">
          <span>{{ card.label }}</span>
          <strong>{{ card.value }}</strong>
          <small v-if="card.help">{{ card.help }}</small>
        </article>
      </div>
    </section>

    <section class="panel" v-if="v3KeyFindings.length">
      <div class="v3-section-head">
        <div>
          <h3>关键结论</h3>
          <p class="muted">把这次运行里最值得先读的信息提到前面。</p>
        </div>
      </div>
      <div class="v3-key-findings">
        <article v-for="item in v3KeyFindings" :key="`${item.label}-${item.value}`" class="v3-key-card">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <small v-if="item.help">{{ item.help }}</small>
        </article>
      </div>
    </section>

    <section class="panel" v-if="v3FlowCards.length">
      <div class="v3-section-head">
        <div>
          <h3>Flow Cards</h3>
          <p class="muted">把 event -> trigger -> follow-up 做成显式流程卡，而不是只读 trace 表格。</p>
        </div>
      </div>
      <div class="planning-node-list v3-layer-grid">
        <article v-for="card in v3FlowCards" :key="`${card.trigger_rule_id}-${card.source_event_id || card.event_type}`" class="planning-node-card">
          <div class="planning-node-top">
            <div class="planning-node-title">
              <span class="planning-node-index">{{ card.event_type }}</span>
              <strong>{{ card.trigger_rule_id }}</strong>
            </div>
            <span class="badge autonomy-status-badge" :class="card.result_label === 'Executed' ? 'badge-ok' : 'badge-warn'">
              {{ card.result_label }}
            </span>
          </div>
          <p class="planning-node-deps muted">follow-up: {{ card.follow_up_label }}</p>
          <p class="planning-node-deps muted">governance: {{ card.governance_label }}</p>
          <pre class="flow-detail-pre">{{ card.summary || card.stop_reason || "No additional summary." }}</pre>
        </article>
      </div>
    </section>

    <section class="panel" v-if="v3GovernanceExplainItems.length">
      <div class="v3-section-head">
        <div>
          <h3>Governance Explain</h3>
          <p class="muted">把允许、拦截、cooldown 和预算限制翻译成用户可读说明。</p>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>Status</th>
            <th>Rule</th>
            <th>Event</th>
            <th>Reason</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in v3GovernanceExplainItems" :key="`${item.rule_id || 'none'}-${item.event_type || 'event'}-${item.label}`">
            <td>{{ item.label }}</td>
            <td>{{ item.rule_id || "—" }}</td>
            <td>{{ item.event_type || "—" }}</td>
            <td>{{ item.reason }}</td>
            <td>{{ item.detail || "—" }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="panel" v-if="v3GraphExecutionNodes.length">
      <div class="v3-section-head">
        <div>
          <h3>执行流程</h3>
          <p class="muted">{{ v3FlowStepLine }}</p>
        </div>
        <span class="badge">{{ v3GraphExecutionNodes.length }} steps</span>
      </div>
      <div class="v3-flow-layout">
        <div class="v3-flow-chain">
          <button
            v-for="(node, index) in v3GraphExecutionNodes"
            :key="node.node_id"
            type="button"
            class="v3-flow-node"
            :class="[
              `is-${node.status}`,
              selectedV3NodeId === node.node_id ? 'is-selected' : '',
            ]"
            @click="selectV3Node(node.node_id)"
          >
            <div class="v3-flow-node-index">#{{ index + 1 }}</div>
            <div class="v3-flow-node-content">
              <div class="v3-flow-node-title">
                <strong>{{ node.skill_name }}</strong>
                <span class="v3-flow-node-id">{{ node.node_id }}</span>
              </div>
              <div class="v3-flow-node-summary">{{ node.summary || "暂无摘要" }}</div>
            </div>
            <span class="v3-flow-node-status">{{ statusLabel(node.status) }}</span>
          </button>
        </div>
        <aside class="v3-flow-detail" v-if="v3SelectedGraphNode">
          <div class="v3-flow-detail-head">
            <h4>当前步骤</h4>
            <span class="status-badge" :class="statusBadgeClass(v3SelectedGraphNode.status)">
              {{ statusLabel(v3SelectedGraphNode.status) }}
            </span>
          </div>
          <div class="v3-flow-detail-meta">
            <p><strong>Skill：</strong>{{ v3SelectedGraphNode.skill_name || "—" }}</p>
            <p><strong>Node ID：</strong>{{ v3SelectedGraphNode.node_id || "—" }}</p>
            <p><strong>Dependencies：</strong>{{ Array.isArray(v3SelectedGraphNode.dependencies) && v3SelectedGraphNode.dependencies.length ? v3SelectedGraphNode.dependencies.join(", ") : "—" }}</p>
          </div>
          <pre class="flow-detail-pre">{{ v3SelectedGraphNode.summary || "暂无摘要。" }}</pre>
        </aside>
      </div>
    </section>

    <nav class="run-tabs" aria-label="V3 detail tabs">
      <button
        v-for="tab in v3Tabs"
        :key="tab.id"
        type="button"
        class="run-tab"
        :class="{ 'is-active': v3ActiveTab === tab.id }"
        @click="v3ActiveTab = tab.id"
      >
        <span>{{ tab.label }}</span>
        <small v-if="tab.hint">{{ tab.hint }}</small>
      </button>
    </nav>

    <section class="panel" v-if="v3ActiveTab === 'graph' && v3Planning">
      <h3>Planning Details</h3>
      <table>
        <tbody>
          <tr><th>goal_kind</th><td>{{ v3Planning.goal_kind || "—" }}</td></tr>
          <tr><th>repo_profile</th><td>{{ v3Planning.repo_profile || "—" }}</td></tr>
          <tr><th>recovery_strategy</th><td>{{ v3Planning.recovery_strategy || "—" }}</td></tr>
          <tr><th>coding_mode</th><td>{{ v3Planning.coding_execution_mode || "—" }}</td></tr>
          <tr><th>rag_ids</th><td>{{ formatRagIds(v3Planning.rag_ids, v3Planning.rag_id) }}</td></tr>
          <tr><th>template</th><td>{{ v3Planning.template_name || "—" }}</td></tr>
          <tr><th>execution_layers</th><td>{{ formatExecutionLayers(v3Planning.execution_layers) }}</td></tr>
        </tbody>
      </table>
      <p class="muted" style="margin-top: 10px">{{ v3Planning.template_reason || "—" }}</p>
    </section>

    <section class="panel" v-if="v3ActiveTab === 'graph' && v3Report">
      <h3>Execution Report</h3>
      <JsonBlock :data="v3Report" />
    </section>

    <section class="panel" v-if="v3ActiveTab === 'trigger' && v3TriggerRules.length">
      <h3>Trigger Rules</h3>
      <div v-if="v3TriggerRules.length" class="v3-trigger-rules-panel">
        <table>
          <thead>
            <tr>
              <th>rule</th>
              <th>target</th>
              <th>enabled</th>
              <th>hit count</th>
              <th>conditions / governance</th>
              <th>action</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="rule in v3TriggerRules" :key="rule.rule_id">
              <td>{{ rule.rule_id }}</td>
              <td>{{ rule.target_skill_name || "—" }}</td>
              <td>
                <span class="badge" :class="isTriggerRuleEnabled(rule.rule_id) ? 'badge-enabled' : 'badge-disabled'">
                  {{ isTriggerRuleEnabled(rule.rule_id) ? "enabled" : "disabled" }}
                </span>
              </td>
              <td>
                {{
                  [
                    `${triggerRuleStats[rule.rule_id]?.executed || 0} executed`,
                    `${triggerRuleStats[rule.rule_id]?.skipped || 0} skipped`,
                  ].join(" / ")
                }}
              </td>
              <td>
                {{
                  [
                    Array.isArray(rule.conditions) && rule.conditions.length ? `conditions=${rule.conditions.length}` : null,
                    rule.cooldown_seconds != null ? `cooldown=${rule.cooldown_seconds}s` : null,
                    rule.max_trigger_count_per_run != null ? `max_count=${rule.max_trigger_count_per_run}` : null,
                  ].filter(Boolean).join(" · ") || "—"
                }}
              </td>
              <td>
                <button class="btn-secondary btn-sm" @click="toggleTriggerRule(rule.rule_id)">
                  {{ isTriggerRuleEnabled(rule.rule_id) ? "临时禁用" : "重新启用" }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <p class="muted" style="margin-top: 10px">
          当前页中的启停仅影响本页展示与调试视图，不会回写历史运行记录。
        </p>
      </div>

      <h3 style="margin-top: 18px">Trigger Follow-ups</h3>
    </section>

    <section class="panel" v-if="v3ActiveTab === 'trigger' && filteredTriggerExecutionNodes.length">
      <h3>Trigger Follow-ups</h3>
      <div class="v3-trigger-section">
        <div class="v3-layer-head">
          <div>
            <p class="muted">事件触发后的补偿动作、修复动作和再验证动作会集中显示在这里。</p>
          </div>
          <span class="badge">{{ filteredTriggerExecutionNodes.length }} nodes</span>
        </div>
        <div class="planning-node-list v3-layer-grid">
          <article
            v-for="node in filteredTriggerExecutionNodes"
            :key="node.node_id"
            class="planning-node-card"
          >
            <div class="planning-node-top">
              <div class="planning-node-title">
                <span class="planning-node-index">#{{ executionNodeIndexMap[node.node_id] }}</span>
                <strong>{{ node.node_id }}</strong>
              </div>
              <span class="agent-version agent-version--v3">
                {{ node.skill_name }}
              </span>
            </div>
            <p class="planning-node-deps muted">
              status: <strong>{{ node.status || "unknown" }}</strong>
              <span> · kind: trigger</span>
              <span v-if="node.source_event_type"> · event: {{ node.source_event_type }}</span>
            </p>
            <p class="planning-node-deps muted">
              parent:
              <span v-if="node.parent_node_id">{{ node.parent_node_id }}</span>
              <span v-else>—</span>
            </p>
            <pre class="flow-detail-pre">{{ node.summary || "暂无摘要。" }}</pre>
          </article>
        </div>
      </div>
    </section>

    <section class="panel" v-if="v3ActiveTab === 'trigger' && filteredTriggerDiagnostics.length">
      <h3>Trigger Diagnostics</h3>
      <table>
        <thead>
          <tr>
            <th>rule</th>
            <th>status</th>
            <th>target skill</th>
            <th>reason / governance</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in filteredTriggerDiagnostics" :key="`${item.trigger_rule_id}-${item.source_event_id || item.parent_node_id || ''}`">
            <td>{{ item.trigger_rule_id }}</td>
            <td>{{ item.status }}</td>
            <td>{{ item.target_skill_name }}</td>
            <td>
              {{
                [
                  item.skip_reason ? `skip=${item.skip_reason}` : null,
                  item.dedupe_key ? `dedupe=${item.dedupe_key}` : null,
                  item.cooldown_key ? `cooldown=${item.cooldown_key}` : null,
                  item.cooldown_seconds != null ? `window=${item.cooldown_seconds}s` : null,
                ].filter(Boolean).join(" · ") || "—"
              }}
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="panel" v-if="v3ActiveTab === 'events'">
      <h3>Events</h3>
      <p class="muted">当前展示的是共享 trace timeline 中和本次 v3 运行相关的事件流。</p>
      <div v-if="v3EventRows.length" class="event-chain-layout">
        <div class="event-chain-events">
          <table>
            <thead>
              <tr>
                <th>type</th>
                <th>source</th>
                <th>created_at</th>
                <th>summary</th>
                <th>action</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(item, index) in v3EventRows"
                :key="`${item.event_id || item.trace_id || index}`"
                :class="{ 'is-selected-row': selectedChainEventId === item.event_id }"
              >
                <td>
                  <div class="event-type-cell">
                    <strong>{{ item.event_type || item.name || "—" }}</strong>
                    <span v-if="item.event_type === 'test_failed'" class="event-type-badge">Recovery Entry</span>
                  </div>
                </td>
                <td>{{ item.source || item.step_type || "—" }}</td>
                <td>{{ item.created_at || item.ts || "—" }}</td>
                <td>{{ summarizeV3Event(item) }}</td>
                <td>
                  <button
                    v-if="canInspectEventChain(item)"
                    class="btn-secondary btn-sm"
                    :disabled="chainLoading && selectedChainEventId === item.event_id"
                    @click="inspectEventChain(item)"
                  >
                    {{
                      chainLoading && selectedChainEventId === item.event_id
                        ? "加载中…"
                        : item.event_type === "test_failed"
                          ? "查看恢复链"
                          : "查看链路"
                    }}
                  </button>
                  <span v-else class="muted">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <aside class="event-chain-panel">
          <div class="event-chain-panel-head">
            <div>
              <h4>Event Chain</h4>
              <p class="muted">点击左侧 `test_failed` 或其它带 `event_id` 的事件，可查看它触发出的后续执行链。</p>
            </div>
            <div class="event-chain-panel-actions">
              <span v-if="eventChain?.item_count" class="badge">{{ eventChain.item_count }} items</span>
              <button
                v-if="selectedChainEventId"
                class="btn-secondary btn-sm"
                :disabled="replayLoading"
                @click="runEventChainReplay"
              >
                {{ replayLoading ? "重放中…" : "重放该链" }}
              </button>
            </div>
          </div>
          <p v-if="chainError" class="error">{{ chainError }}</p>
          <div v-else-if="eventChain" class="event-chain-summary">
            <div class="event-chain-meta">
              <span><strong>root:</strong> {{ eventChain.root_event_type || "—" }}</span>
              <span><strong>chain:</strong> {{ shortChainId(eventChain.execution_chain_id) }}</span>
            </div>
            <div class="event-chain-mini-list">
              <button
                v-for="item in eventChain.items"
                :key="item.event_id"
                type="button"
                class="event-chain-mini-item"
                :class="{ 'is-focus': chainFocusedEventId === item.event_id }"
                @click="chainFocusedEventId = item.event_id"
              >
                <strong>{{ item.event_type }}</strong>
                <span>{{ item.source }}</span>
              </button>
            </div>
            <div v-if="chainFocusedItem" class="event-chain-focus-card">
              <div class="event-chain-focus-head">
                <strong>{{ chainFocusedItem.event_type }}</strong>
                <span>{{ chainFocusedItem.source }}</span>
              </div>
              <p class="muted">
                {{
                  [
                    chainFocusedItem.node_id ? `node=${chainFocusedItem.node_id}` : null,
                    chainFocusedItem.trigger_rule_id ? `rule=${chainFocusedItem.trigger_rule_id}` : null,
                    chainFocusedItem.error ? `error=${chainFocusedItem.error}` : null,
                  ].filter(Boolean).join(" · ") || "无额外元数据"
                }}
              </p>
            </div>
            <div v-if="replayResult" class="event-chain-replay-card">
              <div class="event-chain-focus-head">
                <strong>Replay Result</strong>
                <span :class="replayResult.success ? 'replay-ok' : 'replay-bad'">
                  {{ replayResult.success ? "success" : "failed" }}
                </span>
              </div>
              <p class="muted">{{ replayResult.summary || "—" }}</p>
              <p v-if="replayResult.error" class="error" style="margin: 0">{{ replayResult.error }}</p>
              <div class="event-chain-meta">
                <span><strong>replay_run_id:</strong> {{ shortChainId(replayResult.metadata?.replay_run_id) }}</span>
                <span><strong>skill:</strong> {{ replayResult.metadata?.target_skill_name || "—" }}</span>
              </div>
              <details>
                <summary>查看 Replay Output / Events</summary>
                <JsonBlock :data="replayResult" />
              </details>
            </div>
            <pre class="event-chain-view">{{ eventChainView || "暂无可读视图。" }}</pre>
          </div>
          <p v-else class="muted">尚未选择事件。</p>
        </aside>
      </div>
      <p v-else class="muted">当前 run 没有可单独展示的事件流。</p>
    </section>

    <section class="panel" v-if="v3ActiveTab === 'trace' && trace.length">
      <h3>Trace Snapshot</h3>
      <JsonBlock :data="trace" />
    </section>

    <section class="panel" v-if="v3ActiveTab === 'audit' && v3AuditData">
      <h3>Audit & Replay</h3>
      <div v-if="v3AuditSummary" class="v3-audit-summary">
        <div class="v3-audit-grid">
          <div class="v3-audit-stat">
            <strong>{{ v3AuditSummary.totalRecords }}</strong>
            <span class="muted">Audit Records</span>
          </div>
          <div class="v3-audit-stat">
            <strong>{{ v3AuditSummary.approved }} / {{ v3AuditSummary.totalDecisions }}</strong>
            <span class="muted">Approved Decisions</span>
          </div>
          <div class="v3-audit-stat">
            <strong>{{ v3AuditSummary.governanceActions }}</strong>
            <span class="muted">Governance Actions</span>
          </div>
          <div class="v3-audit-stat">
            <strong>{{ v3AuditSummary.stopReasons }}</strong>
            <span class="muted">Stop Reasons</span>
          </div>
        </div>
      </div>

      <div v-if="v3AuditData.decision_traces?.length" class="v3-audit-section">
        <h4>Decision Traces</h4>
        <table>
          <thead>
            <tr>
              <th>decision</th>
              <th>approved</th>
              <th>reason</th>
              <th>summary</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="dec in v3AuditData.decision_traces" :key="dec.trace_id">
              <td>{{ dec.decision_type }}</td>
              <td>
                <span class="badge" :class="dec.approved ? 'badge-ok' : 'badge-bad'">
                  {{ dec.approved ? "Approved" : "Rejected" }}
                </span>
              </td>
              <td>{{ dec.reason }}</td>
              <td>{{ dec.summary }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="v3AuditData.governance_actions?.length" class="v3-audit-section">
        <h4>Governance Actions</h4>
        <table>
          <thead>
            <tr>
              <th>type</th>
              <th>target</th>
              <th>reason</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="action in v3AuditData.governance_actions" :key="action.action_id">
              <td>{{ action.action_type }}</td>
              <td>{{ action.target_type }}:{{ action.target_id }}</td>
              <td>{{ action.reason }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="v3AuditData.stop_reasons?.length" class="v3-audit-section">
        <h4>Stop Reasons</h4>
        <table>
          <thead>
            <tr>
              <th>type</th>
              <th>actor</th>
              <th>summary</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="sr in v3AuditData.stop_reasons" :key="sr.stop_id">
              <td><span class="badge badge-warn">{{ sr.reason_type }}</span></td>
              <td>{{ sr.actor }}</td>
              <td>{{ sr.summary }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="v3AuditData.records?.length" class="v3-audit-section">
        <h4>Audit Records</h4>
        <table>
          <thead>
            <tr>
              <th>action</th>
              <th>actor</th>
              <th>target</th>
              <th>summary</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="rec in v3AuditData.records" :key="rec.record_id">
              <td>{{ rec.action }}</td>
              <td>{{ rec.actor }}</td>
              <td>{{ rec.target }}</td>
              <td>{{ rec.summary }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </template>

  <nav v-else class="run-tabs" aria-label="Run detail tabs">
    <button
      v-for="tab in tabs"
      :key="tab.id"
      type="button"
      class="run-tab"
      :class="{ 'is-active': activeTab === tab.id }"
      @click="activeTab = tab.id"
    >
      <span>{{ tab.label }}</span>
      <small v-if="tab.hint">{{ tab.hint }}</small>
    </button>
  </nav>

  <template v-if="!isV3Detail && activeTab === 'execution'">
  <section class="panel" v-if="replay.run">
    <h3>运行摘要</h3>
    <table>
      <tbody>
        <tr><th>status</th><td>{{ replay.run.status }}</td></tr>
        <tr><th>session_id</th><td>{{ replay.run.session_id }}</td></tr>
        <tr><th>workdir</th><td>{{ replay.run.workdir || "—" }}</td></tr>
        <tr><th>task</th><td>{{ replay.run.task }}</td></tr>
        <tr><th>model</th><td>{{ replay.run.model }}</td></tr>
        <tr><th>step_count</th><td>{{ replay.run.step_count }}</td></tr>
      </tbody>
    </table>
  </section>

  <section class="panel" v-if="flowNodes.length">
    <h3>执行流程（可视化）</h3>
    <p v-if="flowStepLine" class="flow-step-line muted">{{ flowStepLine }}</p>
    <div class="flow-legend">
      <span class="flow-legend-item"><i class="dot dot-completed" /> 已完成</span>
      <span class="flow-legend-item"><i class="dot dot-running" /> 进行中</span>
      <span class="flow-legend-item"><i class="dot dot-failed" /> 失败</span>
      <span class="flow-legend-item"><i class="dot dot-unknown" /> 未确定</span>
    </div>
    <div class="flow-layout">
      <div
        class="flow-lane"
        tabindex="0"
        role="group"
        :aria-label="'执行流程，共 ' + flowNodes.length + ' 步，方向键可切换节点'"
        @keydown="onFlowKeydown"
      >
        <div class="flow-chain" role="presentation">
          <template v-for="(node, index) in flowNodes" :key="node.id">
            <button
              type="button"
              class="flow-node-btn"
              :class="[
                `is-${normalizeStatus(node.status)}`,
                selectedDelegationId === node.id ? 'is-selected' : '',
              ]"
              :data-node-id="node.id"
              :aria-selected="selectedDelegationId === node.id"
              :ref="(el) => setNodeRef(node.id, el)"
              @click="selectDelegation(node.id)"
            >
              <span class="flow-node-index">#{{ index + 1 }}</span>
              <span class="flow-node-agent">
              <span
                v-if="normalizeStatus(node.status) === 'failed'"
                class="flow-node-fail-mark"
                aria-hidden="true"
                >!</span
              >{{ node.agent }}
            </span>
              <span class="flow-node-status">{{ statusLabel(node.status) }}</span>
              <span class="flow-node-time">{{ node.startedAtLabel }}</span>
            </button>
            <span
              v-if="index < flowNodes.length - 1"
              class="flow-connector"
              aria-hidden="true"
            />
          </template>
        </div>
      </div>
      <aside class="flow-detail">
        <div class="flow-detail-header">
          <h4>节点摘要（只读）</h4>
          <button
            type="button"
            class="btn-secondary btn-compact"
            :disabled="!summaryCopyable"
            @click="copySelectedSummary"
          >
            {{ copyHint }}
          </button>
        </div>
        <template v-if="selectedDelegation">
          <div class="flow-detail-meta">
            <p class="muted"><strong>Agent：</strong>{{ selectedDelegation.target_agent || "—" }}</p>
            <p class="muted">
              <strong>状态：</strong>{{ statusLabel(selectedDelegation.status) }}
            </p>
            <p class="muted"><strong>Step ID：</strong>{{ selectedDelegation.step_id || "—" }}</p>
            <p class="muted"><strong>开始：</strong>{{ formatTime(selectedDelegation.started_at) }}</p>
            <p class="muted"><strong>结束：</strong>{{ formatTime(selectedDelegation.finished_at) }}</p>
            <p class="muted"><strong>耗时：</strong>{{ durationLabel(selectedDelegation.started_at, selectedDelegation.finished_at) }}</p>
          </div>
          <pre class="flow-detail-pre">{{ selectedDelegation.summary || "暂无摘要。" }}</pre>
        </template>
        <p v-else class="muted">点击上方流程中的节点查看摘要；焦点在流程区域时可用 ← → 或 ↑ ↓ 切换。</p>
      </aside>
    </div>
  </section>

  <section class="panel" v-if="finalOutput">
    <h3>最终答案</h3>
    <pre>{{ finalOutput }}</pre>
  </section>

  <section class="panel" v-if="teachingView">
    <h3>教学视图</h3>
    <table>
      <tbody>
        <tr v-if="teachingView.summary"><th>summary</th><td>{{ teachingView.summary }}</td></tr>
        <tr v-if="keyTakeaways.length">
          <th>key_takeaways</th>
          <td>
            <ul class="flat-list">
              <li v-for="item in keyTakeaways" :key="item">{{ item }}</li>
            </ul>
          </td>
        </tr>
      </tbody>
    </table>
  </section>

  <section class="panel" v-if="replay.workspace">
    <h3>Workspace 核心字段</h3>
    <table>
      <tbody>
        <tr><th>user_goal</th><td>{{ replay.workspace.user_goal }}</td></tr>
        <tr><th>project_summary</th><td>{{ replay.workspace.project_summary }}</td></tr>
        <tr><th>latest_patch_summary</th><td>{{ replay.workspace.latest_patch_summary }}</td></tr>
      </tbody>
    </table>
  </section>

  <section class="panel" v-if="replay.execution_log?.length">
    <h3>Execution Log（最近 10 条）</h3>
    <table>
      <thead>
        <tr>
          <th>actor</th>
          <th>action</th>
          <th>status</th>
          <th>message</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in recentLogs" :key="item.event_id || item.id">
          <td>{{ item.actor }}</td>
          <td>{{ item.action }}</td>
          <td>{{ item.status }}</td>
          <td>{{ item.message }}</td>
        </tr>
      </tbody>
    </table>
  </section>
  </template>

  <template v-else-if="!isV3Detail && activeTab === 'memory'">
    <section class="panel memory-panel" v-if="replay.workspace">
      <div class="memory-panel-head">
        <div>
          <h3>Memory / Workspace</h3>
          <p class="muted">
            只读展示本次运行的 shared workspace、各 Agent private memory、artifact 索引与上下文治理信息。
          </p>
        </div>
        <div class="memory-stats">
          <span class="memory-stat"><strong>{{ privateMemoryEntries.length }}</strong> private contexts</span>
          <span class="memory-stat"><strong>{{ artifactsIndex.length }}</strong> artifacts</span>
          <span class="memory-stat"><strong>{{ executionNotes.length }}</strong> notes</span>
          <span class="memory-stat" :class="plannerRagShortcutApplied === true ? 'is-positive' : 'is-neutral'">
            <strong>RAG shortcut</strong> {{ plannerRagShortcutLabel }}
          </span>
        </div>
      </div>

      <div class="memory-grid">
        <article class="memory-card">
          <h4>Shared Workspace</h4>
          <table class="memory-table">
            <tbody>
              <tr v-for="row in sharedWorkspaceRows" :key="row.key">
                <th>{{ row.key }}</th>
                <td>{{ row.value }}</td>
              </tr>
            </tbody>
          </table>
        </article>

        <article class="memory-card">
          <h4>Memory Policy / Context Builder</h4>
          <p class="muted">
            当前展示的是运行时落入 workspace 的策略快照与上下文治理线索；用于确认“哪些状态会进入不同 Agent 的上下文”。
          </p>
          <JsonBlock :data="memoryPolicyView" />
        </article>
      </div>

      <section class="memory-section">
        <div class="memory-section-title">
          <h4>Agent Private Memory</h4>
          <span class="muted">按 Agent 分区保存，避免所有 Agent 共享全量历史。</span>
        </div>
        <div v-if="privateMemoryEntries.length" class="private-memory-grid">
          <article
            v-for="entry in privateMemoryEntries"
            :key="entry.agentId"
            class="private-memory-card"
          >
            <div class="private-memory-head">
              <span class="agent-chip">{{ entry.agentId }}</span>
              <span class="muted">{{ entry.fieldCount }} fields</span>
            </div>
            <JsonBlock :data="entry.payload" />
          </article>
        </div>
        <p v-else class="muted">暂无 private context。</p>
      </section>

      <section class="memory-section">
        <div class="memory-section-title">
          <h4>Artifacts Index</h4>
          <span class="muted">Workspace 中登记的 plan / analysis / patch / review 等工件索引。</span>
        </div>
        <table v-if="artifactsIndex.length">
          <thead>
            <tr>
              <th>key</th>
              <th>type</th>
              <th>version</th>
              <th>summary</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="artifact in artifactsIndex" :key="`${artifact.key}-${artifact.version}`">
              <td>{{ artifact.key }}</td>
              <td>{{ artifact.type }}</td>
              <td>{{ artifact.version }}</td>
              <td>{{ artifact.summary }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted">暂无 artifact 索引。</p>
      </section>

      <section class="memory-section">
        <div class="memory-section-title">
          <h4>Execution Notes</h4>
          <span class="muted">Orchestrator 写入 workspace 的执行备注。</span>
        </div>
        <ol v-if="executionNotes.length" class="memory-notes">
          <li v-for="(note, index) in executionNotes" :key="`${index}-${note}`">{{ note }}</li>
        </ol>
        <p v-else class="muted">暂无 execution notes。</p>
      </section>
    </section>

    <section v-else class="panel">
      <h3>Memory / Workspace</h3>
      <p class="muted">当前 run 没有可展示的 workspace 快照。</p>
    </section>
  </template>
</template>

<script setup>
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import { getRunDetail, getV3EventChain, getV3EventChainView, replayV3EventChain } from "../api";
import JsonBlock from "../components/JsonBlock.vue";
import { formatGovernanceCount, normalizeV3RuntimeSummary } from "../v3RuntimeSummary";

const props = defineProps({
  runId: { type: String, required: true },
});

const router = useRouter();
const route = useRoute();
const error = ref("");
const polling = ref(true);
const activeTab = ref("execution");
const v3ActiveTab = ref("graph");
const detailVersion = ref(String(route.query.version || "").trim().toLowerCase());
const replay = reactive({
  run: null,
  workspace: null,
  delegations: [],
  execution_log: [],
  teaching_view: null,
  artifacts: [],
  audit: null,
});
const trace = ref([]);
const v3Report = ref(null);
const v3Planning = ref(null);
const v3TriggerDiagnostics = ref([]);
const v3ExecutionNodes = ref([]);
const v3RuntimeSummary = ref(normalizeV3RuntimeSummary(null));
const v3TriggerRuleStates = ref({});
const eventChain = ref(null);
const eventChainView = ref("");
const chainLoading = ref(false);
const chainError = ref("");
const selectedChainEventId = ref("");
const chainFocusedEventId = ref("");
const replayLoading = ref(false);
const replayResult = ref(null);
const selectedDelegationId = ref("");
const selectedV3NodeId = ref("");
const nodeEls = ref(new Map());
const copyHint = ref("复制摘要");
const isV3Detail = computed(() => detailVersion.value === "v3");
const v3GraphExecutionNodes = computed(() => {
  return v3ExecutionNodes.value.filter((node) => String(node?.kind || "graph") !== "trigger");
});
const v3TriggerExecutionNodes = computed(() => {
  return v3ExecutionNodes.value.filter((node) => String(node?.kind || "") === "trigger");
});
const v3TriggerRules = computed(() => {
  return Array.isArray(v3Planning.value?.trigger_rules) ? v3Planning.value.trigger_rules : [];
});
const triggerRuleStats = computed(() => {
  return v3TriggerDiagnostics.value.reduce((acc, item) => {
    const key = String(item?.trigger_rule_id || "");
    if (!key) {
      return acc;
    }
    if (!acc[key]) {
      acc[key] = { executed: 0, skipped: 0 };
    }
    if (item.status === "executed") {
      acc[key].executed += 1;
    } else if (item.status === "skipped") {
      acc[key].skipped += 1;
    }
    return acc;
  }, {});
});
const filteredTriggerExecutionNodes = computed(() => {
  return v3TriggerExecutionNodes.value.filter((node) => isTriggerRuleEnabled(node.trigger_rule_id));
});
const filteredTriggerDiagnostics = computed(() => {
  return v3TriggerDiagnostics.value.filter((item) => {
    if (item.trigger_rule_id === "__governance__") {
      return true;
    }
    return isTriggerRuleEnabled(item.trigger_rule_id);
  });
});
const executionNodeIndexMap = computed(() => {
  return v3ExecutionNodes.value.reduce((acc, node, index) => {
    if (node?.node_id) {
      acc[node.node_id] = index + 1;
    }
    return acc;
  }, {});
});
const v3GraphLayerSections = computed(() => {
  const graphNodes = v3GraphExecutionNodes.value;
  if (!graphNodes.length) {
    return [];
  }
  const layers = Array.isArray(v3Planning.value?.execution_layers)
    ? v3Planning.value.execution_layers
    : [];
  const nodesById = new Map(
    graphNodes
      .filter((node) => typeof node?.node_id === "string" && node.node_id)
      .map((node) => [node.node_id, node])
  );
  const usedNodeIds = new Set();
  const sections = layers
    .map((layer, index) => {
      const nodeIds = Array.isArray(layer) ? layer : [];
      const nodes = nodeIds
        .map((nodeId) => nodesById.get(nodeId))
        .filter(Boolean);
      nodes.forEach((node) => usedNodeIds.add(node.node_id));
      if (!nodes.length) {
        return null;
      }
      return {
        id: `layer-${index + 1}`,
        label: `Layer ${index + 1}`,
        description: nodeIds.join(" -> "),
        nodes,
      };
    })
    .filter(Boolean);

  const unlayeredNodes = graphNodes.filter((node) => !usedNodeIds.has(node.node_id));
  if (unlayeredNodes.length) {
    sections.push({
      id: "layer-unassigned",
      label: layers.length ? "Unassigned Graph Nodes" : "Graph Nodes",
      description: layers.length
        ? "这些节点没有被 planning.execution_layers 收录，单独列出便于排查。"
        : "当前 planning 没有 execution_layers，按图节点顺序展示。",
      nodes: unlayeredNodes,
    });
  }
  return sections;
});
const v3EventRows = computed(() => {
  return Array.isArray(trace.value) ? trace.value : [];
});
const v3RunModeCard = computed(() => {
  const runMode = v3RuntimeSummary.value.run_mode;
  if (!runMode) {
    return { value: "—", help: "" };
  }
  return {
    value: runMode.label || runMode.id || "—",
    help: runMode.description || "",
  };
});
const v3FlowCards = computed(() => {
  return Array.isArray(v3RuntimeSummary.value.flow_cards) ? v3RuntimeSummary.value.flow_cards : [];
});
const v3GovernanceExplainItems = computed(() => {
  const summary = v3RuntimeSummary.value.governance_summary;
  return Array.isArray(summary?.items) ? summary.items : [];
});
const v3RecoverySummary = computed(() => {
  return v3RuntimeSummary.value.recovery_summary || {
    status: "not_triggered",
    label: "No Recovery Triggered",
    trigger_skill_name: null,
    parent_node_id: null,
    patch_summary: "",
    verification_summary: "",
    stop_reason: null,
    recovered_node_ids: [],
  };
});
const v3RuntimeExplanation = computed(() => {
  const runMode = v3RuntimeSummary.value.run_mode;
  const flowCards = v3FlowCards.value;
  const governanceItems = v3GovernanceExplainItems.value;
  const recovery = v3RecoverySummary.value;

  const lines = [];

  if (runMode && runMode.id !== "graph_only") {
    lines.push(`### Runtime Mode`);
    lines.push(`- **${runMode.label}**: ${runMode.description || ""}`);
    lines.push("");
  }

  if (flowCards.length > 0) {
    lines.push(`### Event -> Trigger -> Follow-up`);
    for (const card of flowCards) {
      const eventType = card.event_type || "unknown";
      const triggerRule = card.trigger_rule_id || "—";
      const followUp = card.follow_up_label || "no follow-up";
      const govLabel = card.governance_label || "allowed";
      lines.push(`- event: ${eventType} → trigger: ${triggerRule} → follow-up: ${followUp} → governance: ${govLabel}`);
    }
    lines.push("");
  }

  if (governanceItems.length > 0) {
    lines.push(`### Governance Decisions`);
    for (const item of governanceItems) {
      const status = item.status || "unknown";
      const reason = item.reason || "—";
      lines.push(`- ${status}: ${reason}`);
    }
    lines.push("");
  }

  if (recovery.status !== "not_triggered") {
    lines.push(`### Recovery Path`);
    lines.push(`- **Status**: ${recovery.label || recovery.status}`);
    if (recovery.patch_summary) {
      lines.push(`- **Patch**: ${recovery.patch_summary}`);
    }
    if (recovery.verification_summary) {
      lines.push(`- **Verification**: ${recovery.verification_summary}`);
    }
    if (recovery.stop_reason) {
      lines.push(`- **Stop Reason**: ${recovery.stop_reason}`);
    }
    lines.push("");
  }

  return lines.join("\n");
});
const v3FinalSummary = computed(() => {
  const graphNodes = v3GraphExecutionNodes.value;
  const meaningfulNodeSummary = graphNodes
    .map((node) => compactText(node?.summary || "", 220))
    .find((text) => text && text !== "—");
  if (meaningfulNodeSummary) {
    return meaningfulNodeSummary;
  }

  const planning = v3Planning.value || {};
  if (planning.goal_kind === "analysis") {
    const repoProfile = planning.repo_profile || "unknown";
    return `Repository analysis completed. Detected repo profile: ${repoProfile}.`;
  }

  if (typeof planning.template_reason === "string" && planning.template_reason.trim()) {
    return planning.template_reason.trim();
  }

  if (typeof replay.run?.task === "string" && replay.run.task.trim()) {
    return `Run completed for task: ${compactText(replay.run.task.trim(), 160)}`;
  }

  if (typeof replay.run?.status === "string" && replay.run.status.trim()) {
    return `Run finished with status: ${replay.run.status.trim()}.`;
  }

  return "暂无摘要。";
});
const v3PrimaryAnswer = computed(() => {
  const planning = v3Planning.value || {};
  const report = v3Report.value || {};
  let answer = "";
  if (planning.goal_kind === "analysis") {
    answer = composeV3AnalysisAnswer({
      planning,
      report,
      analysisSummary: v3AnalysisSummary.value,
    });
  } else if (planning.goal_kind === "coding") {
    answer = composeV3CodingAnswer({
      planning,
      report,
      codingSummary: v3GraphExecutionNodes.value.find((node) => node?.skill_name === "coding")?.summary || "",
    });
  } else if (planning.goal_kind === "testing") {
    answer = composeV3TestingAnswer({
      planning,
      report,
      recoverySummary: v3RecoverySummary.value,
    });
  } else {
    answer = v3AnalysisSummary.value || v3FinalSummary.value;
  }

  const runtimeExplanation = v3RuntimeExplanation.value;
  if (runtimeExplanation && runtimeExplanation.trim()) {
    answer += "\n\n---\n\n" + runtimeExplanation;
  }

  return answer;
});
const v3SummaryHighlights = computed(() => {
  const planning = v3Planning.value || {};
  const analyzeRepo = v3Report.value?.shared_state?.analyze_repo || v3Report.value?.node_outputs?.analyze_repo || {};
  const highlights = [
    planning.goal_kind ? `goal: ${planning.goal_kind}` : null,
    planning.repo_profile ? `profile: ${planning.repo_profile}` : null,
    Array.isArray(analyzeRepo.root_entries) && analyzeRepo.root_entries.length
      ? `${analyzeRepo.root_entries.length} root entries`
      : null,
    analyzeRepo.has_python_tests === true
      ? "python tests detected"
      : analyzeRepo.has_python_tests === false
        ? "no python tests detected"
        : null,
    Array.isArray(planning.execution_layers) && planning.execution_layers.length
      ? `${planning.execution_layers.length} execution layer${planning.execution_layers.length > 1 ? "s" : ""}`
      : null,
  ];
  return highlights.filter(Boolean);
});
const v3OverviewCards = computed(() => {
  const run = replay.run || {};
  const planning = v3Planning.value || {};
  return [
    {
      label: "状态",
      value: statusLabel(run.status || "unknown"),
      help: planning.planning_mode === "llm" ? "本次规划已使用模型" : "本次规划使用规则模板",
    },
    {
      label: "规划模式",
      value: planning.planning_mode || "rule_based",
      help: planning.template_name ? `template: ${planning.template_name}` : "",
    },
    {
      label: "执行节点",
      value: `${v3GraphExecutionNodes.value.length}`,
      help: Array.isArray(planning.execution_layers) && planning.execution_layers.length
        ? `${planning.execution_layers.length} layers`
        : "single path",
    },
    {
      label: "仓库画像",
      value: planning.repo_profile || "—",
      help: planning.goal_kind ? `goal: ${planning.goal_kind}` : "",
    },
  ];
});
const v3KeyFindings = computed(() => {
  const planning = v3Planning.value || {};
  const notes = Array.isArray(planning.planner_notes) ? planning.planner_notes : [];
  const analyzeRepo = v3Report.value?.shared_state?.analyze_repo || v3Report.value?.node_outputs?.analyze_repo || {};
  const rows = [
    planning.goal_kind ? { label: "任务类型", value: planning.goal_kind, help: planning.template_reason || "" } : null,
    planning.repo_profile ? { label: "仓库画像", value: planning.repo_profile, help: "" } : null,
    v3RecoverySummary.value.status !== "not_triggered"
      ? {
          label: "Recovery",
          value: v3RecoverySummary.value.label,
          help: v3RecoverySummary.value.patch_summary || v3RecoverySummary.value.stop_reason || "",
        }
      : null,
    Array.isArray(analyzeRepo.root_entries) && analyzeRepo.root_entries.length
      ? { label: "根目录规模", value: `${analyzeRepo.root_entries.length} 个入口`, help: compactText(analyzeRepo.root_entries.slice(0, 6).join(", "), 120) }
      : null,
    analyzeRepo.has_python_tests === true
      ? { label: "测试情况", value: "检测到 Python tests", help: "" }
      : analyzeRepo.has_python_tests === false
        ? { label: "测试情况", value: "未检测到 Python tests", help: "" }
        : null,
    notes[0] ? { label: "Planner Note", value: notes[0], help: notes[1] || "" } : null,
  ];
  return rows.filter(Boolean);
});
const v3OutcomeCards = computed(() => {
  const planning = v3Planning.value || {};
  const report = v3Report.value || {};
  const analyzeRepo = report?.shared_state?.analyze_repo || report?.node_outputs?.analyze_repo || {};
  const candidateCommands = Array.isArray(analyzeRepo.candidate_test_commands)
    ? analyzeRepo.candidate_test_commands
    : Array.isArray(planning.candidate_test_commands)
      ? planning.candidate_test_commands
      : [];
  const rootEntries = Array.isArray(analyzeRepo.root_entries) ? analyzeRepo.root_entries : [];

  const outcomeValue = (() => {
    if (planning.goal_kind === "analysis") {
      return `Completed repository analysis for ${planning.repo_profile || "generic"} workspace`;
    }
    if (planning.goal_kind === "testing" && v3RecoverySummary.value.status === "recovered") {
      return "Recovery path completed and retest passed";
    }
    if (planning.goal_kind === "testing" && v3RecoverySummary.value.status === "recovery_failed") {
      return "Recovery triggered but did not converge";
    }
    if (replay.run?.status) {
      return `Run ${String(replay.run.status).toLowerCase()}`;
    }
    return "Run completed";
  })();

  const nextStepValue = (() => {
    if (planning.goal_kind === "analysis") {
      if (candidateCommands.length) {
        return `Run verification with ${candidateCommands[0]}`;
      }
      return "Pick one concrete area and continue with a scoped coding or review task";
    }
    if (planning.goal_kind === "coding") {
      return candidateCommands.length
        ? `Verify the patch with ${candidateCommands[0]}`
        : "Review the changed area and define a verification step";
    }
    if (planning.goal_kind === "testing" && v3RecoverySummary.value.status === "recovered") {
      return "Use this run as the stable trigger recovery demo, then walk through flow cards and trigger follow-ups";
    }
    if (planning.goal_kind === "testing" && v3RecoverySummary.value.status === "recovery_failed") {
      return "Inspect why the recovery step stopped, then compare it with the successful recovery demo";
    }
    return "Continue with the next concrete task based on this output";
  })();

  const riskValue = (() => {
    const risks = [];
    if (analyzeRepo.has_python_tests === false) {
      risks.push("no python tests detected");
    }
    if (!candidateCommands.length) {
      risks.push("no candidate test command");
    }
    if (v3RecoverySummary.value.status === "recovery_failed") {
      risks.push(v3RecoverySummary.value.stop_reason || "recovery did not converge");
    }
    if ((planning.repo_profile || "") === "generic") {
      risks.push("repo profile is generic");
    }
    if (rootEntries.length >= 20) {
      risks.push("large root surface");
    }
    return risks.length ? risks.join(" · ") : "no obvious execution risk captured";
  })();

  return [
    {
      label: "Outcome",
      value: outcomeValue,
      help: planning.template_reason || "",
    },
    {
      label: "Next Step",
      value: nextStepValue,
      help: candidateCommands.length ? `candidate commands: ${candidateCommands.slice(0, 2).join(" / ")}` : "",
    },
    {
      label: "Risks",
      value: riskValue,
      help: rootEntries.length ? `root entries: ${rootEntries.length}` : "",
    },
  ];
});
const v3AnalysisSummary = computed(() => {
  const summaryNode = v3ExecutionNodes.value.find((n) => n.node_id === "analysis_summary");
  if (summaryNode?.summary) {
    return summaryNode.summary;
  }
  const output = v3Report.value?.node_outputs?.analysis_summary;
  if (output?.summary) {
    return output.summary;
  }
  const codingNode = v3ExecutionNodes.value.find((n) => n.skill_name === "coding" && n.summary);
  if (codingNode?.summary) {
    return codingNode.summary;
  }
  return null;
});
const v3AuditData = computed(() => {
  const audit = replay.audit;
  if (!audit || typeof audit !== "object") {
    return null;
  }
  return {
    summary: audit.summary || null,
    records: Array.isArray(audit.records) ? audit.records : [],
    decision_traces: Array.isArray(audit.decision_traces) ? audit.decision_traces : [],
    governance_actions: Array.isArray(audit.governance_actions) ? audit.governance_actions : [],
    stop_reasons: Array.isArray(audit.stop_reasons) ? audit.stop_reasons : [],
  };
});
const v3AuditSummary = computed(() => {
  const summary = v3AuditData.value?.summary;
  if (!summary || typeof summary !== "object") {
    return null;
  }
  return {
    totalRecords: summary.total_audit_records || 0,
    totalDecisions: summary.total_decisions || 0,
    approved: summary.approved_decisions || 0,
    governanceActions: summary.total_governance_actions || 0,
    stopReasons: summary.total_stop_reasons || 0,
  };
});
const v3SelectedGraphNode = computed(() => {
  if (!v3GraphExecutionNodes.value.length) {
    return null;
  }
  return v3GraphExecutionNodes.value.find((node) => node.node_id === selectedV3NodeId.value) || v3GraphExecutionNodes.value[0];
});
const v3FlowStepLine = computed(() => {
  const total = v3GraphExecutionNodes.value.length;
  if (!total) {
    return "暂无执行步骤。";
  }
  const currentIndex = v3GraphExecutionNodes.value.findIndex((node) => node.node_id === v3SelectedGraphNode.value?.node_id);
  const current = currentIndex >= 0 ? currentIndex + 1 : 1;
  return `共 ${total} 步，当前查看第 ${current} 步。`;
});
function formatTokens(run) {
  if (!run) return "—";
  const total = run.total_tokens || 0;
  if (total === 0) return "—";
  return `${total.toLocaleString()}`;
}
function statusBadgeClass(status) {
  const s = String(status || "").toLowerCase();
  if (s === "completed") return "badge-ok";
  if (s === "failed") return "badge-bad";
  if (s === "partial_completed") return "badge-warn";
  return "badge-muted";
}
function renderMarkdown(text) {
  if (!text) return "";
  return text
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/\n/g, "<br>");
}
const chainFocusedItem = computed(() => {
  const items = Array.isArray(eventChain.value?.items) ? eventChain.value.items : [];
  if (!items.length) {
    return null;
  }
  return items.find((item) => item.event_id === chainFocusedEventId.value) || items[0];
});
const v3Tabs = computed(() => [
  {
    id: "graph",
    label: "Graph",
    hint: v3GraphExecutionNodes.value.length ? `${v3GraphExecutionNodes.value.length} nodes` : "",
  },
  {
    id: "trigger",
    label: "Trigger",
    hint: v3TriggerExecutionNodes.value.length || v3TriggerDiagnostics.value.length
      ? `${v3TriggerExecutionNodes.value.length}/${v3TriggerDiagnostics.value.length}`
      : "",
  },
  {
    id: "events",
    label: "Events",
    hint: v3EventRows.value.length ? `${v3EventRows.value.length} items` : "",
  },
  {
    id: "audit",
    label: "Audit",
    hint: v3AuditData.value ? "replay & explain" : "",
  },
  {
    id: "trace",
    label: "Trace",
    hint: trace.value.length ? `${trace.value.length} events` : "",
  },
]);

const tabs = computed(() => [
  {
    id: "execution",
    label: "Execution",
    hint: replay.delegations?.length ? `${replay.delegations.length} delegations` : "",
  },
  {
    id: "memory",
    label: "Memory / Workspace",
    hint: replay.workspace ? `${privateMemoryEntries.value.length} agents` : "",
  },
]);

function setNodeRef(id, el) {
  if (el) {
    nodeEls.value.set(id, el);
  } else {
    nodeEls.value.delete(id);
  }
}

const recentLogs = computed(() => {
  const logs = Array.isArray(replay.execution_log) ? replay.execution_log : [];
  return logs.slice(-10).reverse();
});

const finalOutput = computed(() => {
  return typeof replay.run?.final_output === "string" ? replay.run.final_output : "";
});

const teachingView = computed(() => {
  return replay.teaching_view && typeof replay.teaching_view === "object" ? replay.teaching_view : null;
});

const keyTakeaways = computed(() => {
  const items = teachingView.value?.key_takeaways;
  return Array.isArray(items) ? items : [];
});
const workspace = computed(() => {
  return replay.workspace && typeof replay.workspace === "object" ? replay.workspace : null;
});
const artifactsIndex = computed(() => {
  const items = workspace.value?.artifacts_index;
  return Array.isArray(items) ? items : [];
});
const executionNotes = computed(() => {
  const items = workspace.value?.execution_notes;
  return Array.isArray(items) ? items : [];
});
const privateContext = computed(() => {
  const value = workspace.value?.private_context;
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
});
const privateMemoryEntries = computed(() => {
  return Object.entries(privateContext.value)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([agentId, payload]) => ({
      agentId,
      payload,
      fieldCount: payload && typeof payload === "object" && !Array.isArray(payload)
        ? Object.keys(payload).length
        : 0,
    }));
});
const sharedWorkspaceRows = computed(() => {
  const ws = workspace.value || {};
  const orchestrator = privateContext.value.orchestrator || {};
  const ragId = typeof orchestrator.rag_id === "string" && orchestrator.rag_id ? orchestrator.rag_id : "default";
  const ragIds = Array.isArray(orchestrator.rag_ids) ? orchestrator.rag_ids : [ragId];
  return [
    { key: "user_goal", value: compactText(ws.user_goal) },
    { key: "current_plan", value: ws.current_plan?.steps ? `${ws.current_plan.steps.length} steps` : "—" },
    { key: "project_summary", value: compactText(ws.project_summary) },
    { key: "latest_patch_summary", value: compactText(ws.latest_patch_summary) },
    {
      key: "latest_test_result",
      value: ws.latest_test_result
        ? `${ws.latest_test_result.status || "unknown"} · ${compactText(ws.latest_test_result.summary)}`
        : "—",
    },
    { key: "artifacts_index", value: `${artifactsIndex.value.length} items` },
    { key: "execution_notes", value: `${executionNotes.value.length} notes` },
    { key: "rag_id", value: ragId },
    { key: "rag_ids", value: ragIds.join(", ") },
  ];
});
const memoryPolicyView = computed(() => {
  const orchestrator = privateContext.value.orchestrator || {};
  const planMetadata = workspace.value?.current_plan?.metadata || {};
  return {
    policy: orchestrator.policy || null,
    strategy_profile: orchestrator.strategy_profile || null,
    plan_strategy: planMetadata.planner_strategy || null,
    context_builder: {
      shared_workspace_fields: [
        "user_goal",
        "current_plan",
        "project_summary",
        "latest_patch_summary",
        "latest_test_result",
        "artifacts_index",
        "execution_notes",
      ],
      private_memory_agents: privateMemoryEntries.value.map((item) => item.agentId),
      note: "具体 prompt 装配由 ContextBuilder 按 agent 类型选择性读取 workspace/private_context。",
    },
  };
});
const plannerRagShortcutApplied = computed(() => {
  const planMetadata = workspace.value?.current_plan?.metadata || {};
  const plannerStrategy = planMetadata.planner_strategy || {};
  return typeof plannerStrategy.rag_shortcut_applied === "boolean"
    ? plannerStrategy.rag_shortcut_applied
    : null;
});
const plannerRagShortcutLabel = computed(() => {
  if (plannerRagShortcutApplied.value === true) {
    return "ON";
  }
  if (plannerRagShortcutApplied.value === false) {
    return "OFF";
  }
  return "N/A";
});
const flowNodes = computed(() => {
  const rows = Array.isArray(replay.delegations) ? replay.delegations : [];
  return rows.map((item, index) => ({
    id: item.delegation_id || item.task_id || `node-${index}`,
    agent: item.target_agent || "unknown",
    status: item.status || "unknown",
    startedAtLabel: formatTime(item.started_at),
  }));
});
const flowStepLine = computed(() => {
  const n = flowNodes.value.length;
  if (!n) {
    return "";
  }
  const i = flowNodes.value.findIndex((node) => node.id === selectedDelegationId.value);
  const k = i >= 0 ? i + 1 : 1;
  return `共 ${n} 步 · 当前第 ${k} 步`;
});
const selectedDelegation = computed(() => {
  const rows = Array.isArray(replay.delegations) ? replay.delegations : [];
  if (!rows.length) {
    return null;
  }
  const selected = rows.find(
    (item, index) =>
      (item.delegation_id || item.task_id || `node-${index}`) === selectedDelegationId.value
  );
  return selected || rows[0];
});
const summaryCopyable = computed(() => {
  const t = selectedDelegation.value?.summary;
  return typeof t === "string" && t.length > 0;
});

let timerId = null;

function scrollSelectedNodeIntoView() {
  const el = nodeEls.value.get(selectedDelegationId.value);
  if (el && typeof el.scrollIntoView === "function") {
    el.scrollIntoView({ block: "nearest", inline: "nearest" });
  }
}

watch(
  () => [selectedDelegationId.value, flowNodes.value.length],
  () => {
    void nextTick(() => {
      scrollSelectedNodeIntoView();
    });
  },
  { flush: "post" }
);

watch(
  () => v3TriggerRules.value,
  (rules) => {
    const nextStates = {};
    for (const rule of rules) {
      if (!rule?.rule_id) {
        continue;
      }
      const explicit = v3TriggerRuleStates.value[rule.rule_id];
      nextStates[rule.rule_id] = typeof explicit === "boolean" ? explicit : rule.enabled !== false;
    }
    v3TriggerRuleStates.value = nextStates;
  },
  { immediate: true, deep: true }
);

watch(
  () => v3GraphExecutionNodes.value,
  (nodes) => {
    if (!Array.isArray(nodes) || !nodes.length) {
      selectedV3NodeId.value = "";
      return;
    }
    const exists = nodes.some((node) => node?.node_id === selectedV3NodeId.value);
    if (!exists) {
      selectedV3NodeId.value = nodes[0].node_id || "";
    }
  },
  { immediate: true, deep: true }
);

async function fetchReplay() {
  try {
    error.value = "";
    const data = await getRunDetail(props.runId);
    detailVersion.value = normalizeVersion(data.version || route.query.version || "");
    replay.run = data.run || null;
    replay.workspace = data.workspace || null;
    replay.delegations = data.delegations || [];
    replay.execution_log = data.execution_log || [];
    replay.teaching_view = data.teaching_view || null;
    replay.artifacts = data.artifacts || [];
    replay.audit = data.audit || null;
    trace.value = Array.isArray(data.trace) ? data.trace : [];
    v3Report.value = data.report || null;
    v3Planning.value = data.planning || null;
    v3TriggerDiagnostics.value = Array.isArray(data.trigger_diagnostics) ? data.trigger_diagnostics : [];
    v3ExecutionNodes.value = Array.isArray(data.execution_nodes) ? data.execution_nodes : [];
    v3RuntimeSummary.value = normalizeV3RuntimeSummary(data.runtime_summary);
    if (detailVersion.value === "v3" && Array.isArray(v3ExecutionNodes.value) && v3ExecutionNodes.value.length) {
      const graphNode = v3ExecutionNodes.value.find((node) => String(node?.kind || "graph") !== "trigger");
      selectedV3NodeId.value = graphNode?.node_id || "";
    }
    resetEventChainPanel();
    if (detailVersion.value === "v3") {
      polling.value = false;
      stopPolling();
      return;
    }
    if (Array.isArray(replay.delegations) && replay.delegations.length) {
      const currentExists = replay.delegations.some(
        (item, index) =>
          (item.delegation_id || item.task_id || `node-${index}`) === selectedDelegationId.value
      );
      if (!selectedDelegationId.value || !currentExists) {
        const failed = replay.delegations.find(
          (item) => String(item.status || "").toLowerCase() === "failed"
        );
        const fallback = failed || replay.delegations[0];
        const fallbackIndex = replay.delegations.indexOf(fallback);
        selectedDelegationId.value = fallback.delegation_id || fallback.task_id || `node-${fallbackIndex}`;
      }
    }
    const status = data.run?.status;
    if (status === "completed" || status === "failed") {
      polling.value = false;
      stopPolling();
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "读取回放失败";
    polling.value = false;
    stopPolling();
  }
}

function startPolling() {
  timerId = setInterval(fetchReplay, 3000);
}

function stopPolling() {
  if (timerId) {
    clearInterval(timerId);
    timerId = null;
  }
}

function goTrace() {
  router.push({
    name: "trace",
    params: { runId: props.runId },
    query: { version: detailVersion.value || undefined },
  });
}

function canInspectEventChain(item) {
  return Boolean(item && item.event_id && (item.execution_chain_id || item.event_type === "test_failed"));
}

function shortChainId(value) {
  if (!value || typeof value !== "string") return "—";
  if (value.length <= 22) return value;
  return `${value.slice(0, 14)}…${value.slice(-6)}`;
}

function resetEventChainPanel() {
  eventChain.value = null;
  eventChainView.value = "";
  chainLoading.value = false;
  chainError.value = "";
  selectedChainEventId.value = "";
  chainFocusedEventId.value = "";
  replayLoading.value = false;
  replayResult.value = null;
}

function isTriggerRuleEnabled(ruleId) {
  if (!ruleId) {
    return true;
  }
  const current = v3TriggerRuleStates.value[ruleId];
  return typeof current === "boolean" ? current : true;
}

function toggleTriggerRule(ruleId) {
  if (!ruleId) {
    return;
  }
  v3TriggerRuleStates.value = {
    ...v3TriggerRuleStates.value,
    [ruleId]: !isTriggerRuleEnabled(ruleId),
  };
}

async function inspectEventChain(item) {
  if (!canInspectEventChain(item)) {
    return;
  }
  chainLoading.value = true;
  chainError.value = "";
  selectedChainEventId.value = item.event_id || "";
  chainFocusedEventId.value = "";
  try {
    const [chainData, chainText] = await Promise.all([
      getV3EventChain(props.runId, { eventId: item.event_id }),
      getV3EventChainView(props.runId, { eventId: item.event_id }),
    ]);
    eventChain.value = chainData;
    eventChainView.value = chainText;
    chainFocusedEventId.value = Array.isArray(chainData.items) && chainData.items.length ? chainData.items[0].event_id : "";
    replayResult.value = null;
    v3ActiveTab.value = "events";
  } catch (err) {
    eventChain.value = null;
    eventChainView.value = "";
    chainError.value = err instanceof Error ? err.message : "读取事件链失败";
  } finally {
    chainLoading.value = false;
  }
}

async function runEventChainReplay() {
  if (!selectedChainEventId.value) {
    return;
  }
  replayLoading.value = true;
  chainError.value = "";
  try {
    replayResult.value = await replayV3EventChain(props.runId, { eventId: selectedChainEventId.value });
  } catch (err) {
    replayResult.value = null;
    chainError.value = err instanceof Error ? err.message : "重放事件链失败";
  } finally {
    replayLoading.value = false;
  }
}

function summarizeV3Event(item) {
  const payload = item?.payload;
  if (payload && typeof payload === "object") {
    if (typeof payload.summary === "string" && payload.summary.trim()) {
      return payload.summary.trim();
    }
    if (typeof payload.message === "string" && payload.message.trim()) {
      return payload.message.trim();
    }
    if (typeof payload.node_id === "string" && payload.node_id) {
      return `node=${payload.node_id}`;
    }
    if (typeof payload.skill_name === "string" && payload.skill_name) {
      return `skill=${payload.skill_name}`;
    }
  }
  if (typeof item?.summary === "string" && item.summary.trim()) {
    return item.summary.trim();
  }
  return "—";
}

function selectDelegation(id) {
  selectedDelegationId.value = id;
}

function selectV3Node(nodeId) {
  selectedV3NodeId.value = nodeId;
}

function onFlowKeydown(e) {
  const keys = ["ArrowLeft", "ArrowUp", "ArrowRight", "ArrowDown"];
  if (!keys.includes(e.key)) {
    return;
  }
  const list = flowNodes.value;
  if (list.length === 0) {
    return;
  }
  let idx = list.findIndex((n) => n.id === selectedDelegationId.value);
  if (idx < 0) {
    idx = 0;
  }
  if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
    e.preventDefault();
    if (idx > 0) {
      selectDelegation(list[idx - 1].id);
    }
  } else if (e.key === "ArrowRight" || e.key === "ArrowDown") {
    e.preventDefault();
    if (idx < list.length - 1) {
      selectDelegation(list[idx + 1].id);
    }
  }
}

async function copySelectedSummary() {
  const text = selectedDelegation.value?.summary;
  if (typeof text !== "string" || !text.length) {
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    copyHint.value = "已复制";
    window.setTimeout(() => {
      copyHint.value = "复制摘要";
    }, 2000);
  } catch {
    copyHint.value = "复制失败";
    window.setTimeout(() => {
      copyHint.value = "复制摘要";
    }, 2000);
  }
}

function normalizeStatus(status) {
  const s = String(status || "").toLowerCase();
  if (s === "completed") return "completed";
  if (s === "failed") return "failed";
  if (s === "running") return "running";
  return "unknown";
}

function statusLabel(status) {
  const s = String(status || "").toLowerCase();
  if (s === "completed" || s === "done") return "已完成";
  if (s === "failed") return "失败";
  if (s === "partial_completed") return "部分完成";
  if (s === "running") return "进行中";
  if (s === "skipped") return "跳过";
  const raw = String(status || "").trim();
  return raw && raw.toLowerCase() !== "unknown" ? raw : "未确定";
}

function formatTime(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function durationLabel(startedAt, finishedAt) {
  if (!startedAt || !finishedAt) return "—";
  const s = new Date(startedAt).getTime();
  const e = new Date(finishedAt).getTime();
  if (Number.isNaN(s) || Number.isNaN(e) || e < s) return "—";
  const sec = Math.round((e - s) / 1000);
  return `${sec}s`;
}

function compactText(value, maxLength = 180) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  const text = typeof value === "string" ? value : JSON.stringify(value);
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength)}…`;
}

function composeV3AnalysisAnswer({ planning, report, analysisSummary }) {
  if (typeof analysisSummary === "string" && analysisSummary.trim()) {
    const analyzeRepo = report?.shared_state?.analyze_repo || report?.node_outputs?.analyze_repo || {};
    const rootEntries = Array.isArray(analyzeRepo.root_entries) ? analyzeRepo.root_entries : [];
    const importantDirs = rootEntries.filter((item) => ["backend", "frontend", "docs", "data", "src"].includes(String(item))).slice(0, 4);
    const candidateCommands = Array.isArray(analyzeRepo.candidate_test_commands) ? analyzeRepo.candidate_test_commands : [];
    const lines = [
      "### 中文结果摘要",
      `已完成对该项目结构的分析，当前更像一个 **${planning.repo_profile || "generic"}** 画像的工程仓库。`,
      "",
      "### 结构重点",
      `- 仓库画像：${planning.repo_profile || "generic"}`,
      importantDirs.length ? `- 关键目录：${importantDirs.join("、")}` : null,
      rootEntries.length ? `- 根目录入口数：${rootEntries.length}` : null,
      candidateCommands.length ? `- 候选验证命令：${candidateCommands.slice(0, 2).join(" / ")}` : `- 候选验证命令：未识别`,
      "",
      "### 建议下一步",
      candidateCommands.length
        ? `- 如果要继续推进，可以先运行 ${candidateCommands[0]} 做一次环境级验证。`
        : "- 如果要继续推进，建议先选择 backend、frontend 或 data 中的一个子系统做更细分析。",
      "",
      "### 原始详细分析（模型输出）",
      analysisSummary.trim(),
    ];
    return lines.filter(Boolean).join("\n");
  }
  return v3FinalSummary.value;
}

function composeV3CodingAnswer({ planning, report, codingSummary }) {
  const codingText = typeof codingSummary === "string" ? codingSummary.trim() : "";
  const testRunner = report?.node_outputs?.test_runner || {};
  const testSummary = typeof testRunner.summary === "string" ? testRunner.summary.trim() : "";
  const modifiedFiles = Array.isArray(report?.node_outputs?.coding?.modified_files)
    ? report.node_outputs.coding.modified_files
    : [];
  const riskNotes = Array.isArray(report?.node_outputs?.coding?.risk_notes)
    ? report.node_outputs.coding.risk_notes
    : [];
  const lines = ["### 结果"];
  if (codingText) {
    lines.push(codingText);
  } else {
    lines.push("本次编码任务已完成。");
  }
  if (modifiedFiles.length) {
    lines.push("");
    lines.push("### 变更范围");
    lines.push(...modifiedFiles.slice(0, 6).map((item) => `- ${item}`));
  }
  if (testSummary) {
    lines.push("");
    lines.push("### 验证");
    lines.push(`- ${testSummary}`);
  } else if (Array.isArray(planning?.candidate_test_commands) && planning.candidate_test_commands.length) {
    lines.push("");
    lines.push("### 验证");
    lines.push(`- 尚未看到自动验证结果，建议执行：${planning.candidate_test_commands[0]}`);
  }
  lines.push("");
  lines.push("### 风险");
  if (riskNotes.length) {
    lines.push(...riskNotes.slice(0, 4).map((item) => `- ${item}`));
  } else if (testSummary) {
    lines.push("- 当前未记录额外风险，建议结合受影响页面或模块再做一次手工回归。");
  } else {
    lines.push("- 目前缺少明确验证结果，交付前最好补一轮自动或手工验证。");
  }
  return lines.join("\n");
}

function composeV3TestingAnswer({ planning, report, recoverySummary }) {
  const testRunner = report?.node_outputs?.test_runner || {};
  const command = testRunner.executed_command
    || (Array.isArray(planning?.candidate_test_commands) && planning.candidate_test_commands.length ? planning.candidate_test_commands[0] : "");
  const summary = typeof testRunner.summary === "string" && testRunner.summary.trim()
    ? testRunner.summary.trim()
    : "测试任务已完成。";
  const stdout = typeof testRunner.stdout === "string" ? testRunner.stdout.trim() : "";
  const observation = stdout
    ? compactText(stdout.split("\n").filter(Boolean).slice(-3).join(" | "), 180)
    : "未记录额外输出摘要。";
  const recoveryStatus = recoverySummary?.status || "not_triggered";
  const recoveryLine = recoveryStatus === "recovered"
    ? (recoverySummary.verification_summary || "已完成自动补救并重新验证。")
    : recoveryStatus === "recovery_failed"
      ? (recoverySummary.stop_reason || "已触发 recovery，但当前未收敛。")
      : "本次运行没有进入 recovery follow-up。";
  const recoveryPatch = recoverySummary?.patch_summary
    ? `- patch: ${recoverySummary.patch_summary}`
    : null;
  return [
    "### 结果",
    summary,
    "",
    "### 执行命令",
    `- ${command || "未记录"}`,
    "",
    "### 观察",
    `- ${observation}`,
    `- recovery: ${recoveryLine}`,
    ...(recoveryPatch ? [recoveryPatch] : []),
    "",
    "### 建议下一步",
    recoveryStatus === "recovered" || summary.toLowerCase().includes("passed")
      ? "- 当前验证已通过；如果这是一次修复任务，可以继续做手工回归或提交结果。"
      : "- 当前结果需要继续排查失败原因，并决定是否进入修复流程。",
  ].join("\n");
}

function normalizeVersion(v) {
  if (!v || typeof v !== "string") return "";
  const s = v.trim().toLowerCase();
  if (s === "v1" || s === "v2" || s === "v3") return s;
  return s;
}

function formatRagIds(ragIds, ragId) {
  if (Array.isArray(ragIds) && ragIds.length) {
    return ragIds.join(", ");
  }
  if (ragId) {
    return String(ragId);
  }
  return "—";
}

function formatExecutionLayers(layers) {
  if (!Array.isArray(layers) || !layers.length) {
    return "—";
  }
  return layers
    .map((layer) => `[${Array.isArray(layer) ? layer.join(", ") : String(layer)}]`)
    .join(" -> ");
}

onMounted(async () => {
  await fetchReplay();
  if (polling.value && detailVersion.value !== "v3") {
    startPolling();
  }
});

onBeforeUnmount(() => {
  stopPolling();
});
</script>

<style scoped>
.run-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: -6px 0 20px;
}

.run-tab {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 42px;
  padding: 9px 14px;
  border: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
  background: rgba(255, 255, 255, 0.72);
  color: var(--text-secondary, #5c6370);
  box-shadow: 0 1px 2px rgba(15, 20, 25, 0.03);
}

.run-tab small {
  color: var(--text-muted, #8b929e);
  font-size: 0.7rem;
  font-weight: 700;
}

.run-tab.is-active {
  background:
    linear-gradient(135deg, rgba(79, 70, 229, 0.14), rgba(13, 148, 136, 0.08)),
    #fff;
  color: var(--accent-text, #4338ca);
  border-color: rgba(79, 70, 229, 0.28);
  box-shadow: 0 6px 22px rgba(79, 70, 229, 0.12);
}

.memory-panel {
  background:
    radial-gradient(circle at 0 0, rgba(79, 70, 229, 0.08), transparent 34%),
    radial-gradient(circle at 100% 6%, rgba(13, 148, 136, 0.08), transparent 30%),
    var(--bg-elevated, #fff);
}

.v3-layer-list {
  display: grid;
  gap: 16px;
}

.v3-layer-section,
.v3-trigger-section {
  border: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.72);
  padding: 14px;
}

.v3-layer-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.v3-layer-head h4 {
  margin: 0 0 4px;
  font-size: 0.98rem;
}

.v3-layer-head p {
  margin: 0;
}

.v3-layer-grid {
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
}

.v3-trigger-section {
  margin-top: 16px;
}

.v3-trigger-rules-panel {
  border: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
  border-radius: 14px;
  background: rgba(248, 250, 252, 0.78);
  padding: 14px;
}

.event-chain-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.9fr);
  gap: 16px;
  align-items: start;
}

.event-chain-events {
  min-width: 0;
}

.event-chain-panel {
  border: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
  border-radius: 16px;
  background:
    radial-gradient(circle at top right, rgba(79, 70, 229, 0.08), transparent 36%),
    rgba(248, 250, 252, 0.88);
  padding: 16px;
  min-width: 0;
  position: sticky;
  top: 12px;
}

.event-chain-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.event-chain-panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.event-chain-panel-head h4 {
  margin: 0 0 4px;
}

.event-chain-panel-head p {
  margin: 0;
}

.event-chain-summary {
  display: grid;
  gap: 12px;
}

.event-chain-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  font-size: 0.83rem;
  color: var(--text-secondary, #5c6370);
}

.event-chain-mini-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.event-chain-mini-item {
  display: grid;
  gap: 2px;
  min-width: 120px;
  padding: 8px 10px;
  border-radius: 12px;
  border: 1px solid rgba(79, 70, 229, 0.14);
  background: rgba(255, 255, 255, 0.82);
  text-align: left;
}

.event-chain-mini-item strong {
  font-size: 0.78rem;
}

.event-chain-mini-item span {
  font-size: 0.72rem;
  color: var(--text-muted, #8b929e);
}

.event-chain-mini-item.is-focus {
  border-color: rgba(79, 70, 229, 0.35);
  box-shadow: 0 6px 18px rgba(79, 70, 229, 0.12);
  transform: translateY(-1px);
}

.event-chain-focus-card {
  border: 1px solid rgba(15, 20, 25, 0.08);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.76);
  padding: 12px;
}

.event-chain-replay-card {
  border: 1px solid rgba(15, 20, 25, 0.08);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.82);
  padding: 12px;
}

.event-chain-replay-card details {
  margin-top: 10px;
}

.replay-ok {
  color: #047857;
  font-weight: 700;
}

.replay-bad {
  color: #b91c1c;
  font-weight: 700;
}

.event-chain-focus-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.event-chain-view {
  max-height: 420px;
  overflow: auto;
  margin: 0;
  padding: 14px;
  border-radius: 14px;
  background: #0f172a;
  color: #e2e8f0;
  font-size: 0.82rem;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

.event-type-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.event-type-badge {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(220, 38, 38, 0.1);
  color: #b91c1c;
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.02em;
}

.is-selected-row {
  outline: 2px solid rgba(79, 70, 229, 0.16);
  outline-offset: -2px;
  background: rgba(79, 70, 229, 0.04);
}

.memory-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.memory-panel-head h3 {
  margin-bottom: 6px;
}

.memory-stats {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  min-width: 220px;
}

.memory-stat {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 7px 10px;
  border: 1px solid rgba(79, 70, 229, 0.18);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.78);
  color: var(--text-secondary, #5c6370);
  font-size: 0.75rem;
}

.memory-stat strong {
  color: var(--text-primary, #1a1d26);
}

.memory-stat.is-positive {
  border-color: rgba(16, 185, 129, 0.35);
  background: rgba(16, 185, 129, 0.08);
}

.memory-stat.is-neutral {
  border-color: rgba(100, 116, 139, 0.28);
}

.memory-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr);
  gap: 14px;
  margin-bottom: 18px;
}

.memory-card,
.private-memory-card,
.memory-section {
  border: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 1px 2px rgba(15, 20, 25, 0.03);
}

.memory-card {
  padding: 14px;
  min-width: 0;
}

.memory-card h4,
.memory-section h4 {
  margin: 0 0 10px;
  font-size: 0.92rem;
}

.memory-card :deep(pre),
.private-memory-card :deep(pre) {
  max-height: 360px;
  margin: 10px 0 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.memory-table tbody th {
  width: 34%;
}

.memory-section {
  padding: 14px;
  margin-top: 14px;
}

.memory-section-title {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.private-memory-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.private-memory-card {
  min-width: 0;
  padding: 12px;
}

.private-memory-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.agent-chip {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: #0f172a;
  color: #f8fafc;
  font-size: 0.75rem;
  font-weight: 800;
  letter-spacing: 0.02em;
}

.memory-notes {
  margin: 0;
  padding-left: 1.35rem;
  color: var(--text-primary, #1a1d26);
}

.memory-notes li + li {
  margin-top: 6px;
}

.flow-step-line {
  margin: 0 0 8px;
  font-size: 0.8125rem;
}

.flow-layout {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.flow-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 8px 0 14px;
}

.flow-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  color: var(--text-secondary, #5c6370);
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.dot-completed { background: #10b981; }
.dot-running { background: #3b82f6; }
.dot-failed { background: #dc2626; }
.dot-unknown { background: #94a3b8; }

.flow-lane {
  overflow-x: auto;
  padding: 8px 0 12px;
  border-radius: 8px;
  outline: none;
}
.flow-lane:focus-visible {
  box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.25);
}

.flow-chain {
  display: inline-flex;
  flex-direction: row;
  flex-wrap: nowrap;
  align-items: center;
  min-width: min-content;
  width: 100%;
}

.flow-node-fail-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1rem;
  height: 1rem;
  margin-right: 4px;
  border-radius: 50%;
  background: #dc2626;
  color: #fff;
  font-size: 0.65rem;
  font-weight: 800;
  line-height: 1;
  vertical-align: middle;
}

.flow-node-btn {
  border: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
  background: #fff;
  border-radius: 10px;
  padding: 8px 10px;
  min-width: 120px;
  flex: 0 0 auto;
  text-align: left;
  align-self: center;
  cursor: pointer;
}

.flow-node-btn.is-selected {
  box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.22);
  transform: translateY(-1px);
}

.flow-node-index {
  display: inline-block;
  font-size: 0.6875rem;
  color: var(--text-muted, #8b929e);
}

.flow-node-agent {
  display: block;
  font-size: 0.8125rem;
  font-weight: 700;
}

.flow-node-status {
  display: block;
  margin-top: 2px;
  font-size: 0.75rem;
  color: var(--text-muted, #8b929e);
}

.flow-node-time {
  display: block;
  margin-top: 3px;
  font-size: 0.6875rem;
  color: var(--text-muted, #8b929e);
}

.flow-node-btn.is-completed {
  border-color: rgba(16, 185, 129, 0.35);
  background: rgba(16, 185, 129, 0.08);
}

.flow-node-btn.is-failed {
  border: 2px solid rgba(220, 38, 38, 0.65);
  background: rgba(220, 38, 38, 0.12);
  box-shadow: inset 0 0 0 1px rgba(220, 38, 38, 0.1);
}

.flow-node-btn.is-running {
  border-color: rgba(59, 130, 246, 0.35);
  background: rgba(59, 130, 246, 0.08);
}

.flow-connector {
  flex: 0 0 1.25rem;
  height: 2px;
  align-self: center;
  background: var(--border-subtle, rgba(15, 20, 25, 0.18));
  border-radius: 1px;
  opacity: 0.9;
}

.flow-detail {
  border: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
  border-radius: 10px;
  padding: 14px 12px;
  background: #fafbfe;
  margin-top: 6px;
}

.flow-detail-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.flow-detail h4 {
  margin: 0;
  font-size: 0.875rem;
}

.btn-compact {
  padding: 4px 10px;
  font-size: 0.75rem;
  flex-shrink: 0;
}

.flow-detail-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 2px 12px;
  margin-bottom: 6px;
}

.flow-detail-pre {
  max-height: 40vh;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.v3-summary-card {
  margin-top: 14px;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(79, 70, 229, 0.12);
  background:
    linear-gradient(135deg, rgba(79, 70, 229, 0.08), rgba(255, 255, 255, 0.98) 36%),
    #fff;
}

.v3-summary-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.v3-summary-text {
  margin: 0;
  font-size: 0.95rem;
  line-height: 1.6;
  color: var(--text-primary, #111827);
}

.v3-summary-highlights {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.v3-summary-highlights span {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.05);
  color: var(--text-secondary, #475569);
  font-size: 0.78rem;
  font-weight: 600;
}

/* 窄屏：竖向时间轴，少横滑 */
@media (max-width: 640px) {
  .event-chain-layout,
  .memory-panel-head,
  .memory-grid {
    grid-template-columns: 1fr;
    flex-direction: column;
  }
  .event-chain-panel {
    position: static;
  }
  .memory-stats {
    justify-content: flex-start;
    min-width: 0;
  }
  .private-memory-grid {
    grid-template-columns: 1fr;
  }
  .flow-lane {
    overflow-x: visible;
    padding: 8px 0 4px;
  }
  .flow-chain {
    flex-direction: column;
    align-items: stretch;
    min-width: 0;
    max-width: 100%;
  }
  .flow-node-btn {
    width: 100%;
    max-width: 100%;
    min-width: 0;
  }
  .flow-connector {
    flex: none;
    width: 2px;
    height: 0.5rem;
    margin: 0 auto;
  }
  .flow-detail-meta {
    grid-template-columns: 1fr;
  }
}

.v3-run-header {
  margin-bottom: 12px;
}

.v3-result-hero {
  display: grid;
  gap: 16px;
}

.v3-overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.v3-overview-card,
.v3-key-card,
.v3-flow-detail {
  border: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.84);
  box-shadow: 0 1px 2px rgba(15, 20, 25, 0.03);
}

.v3-overview-card,
.v3-key-card {
  display: grid;
  gap: 6px;
  padding: 14px;
}

.v3-overview-card span,
.v3-key-card span {
  font-size: 0.74rem;
  font-weight: 800;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--text-muted, #8b929e);
}

.v3-overview-card strong,
.v3-key-card strong {
  font-size: 1rem;
  color: var(--text-primary, #1a1d26);
}

.v3-overview-card small,
.v3-key-card small {
  color: var(--text-secondary, #5c6370);
  line-height: 1.45;
}

.v3-primary-answer-head,
.v3-section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.v3-primary-answer-head h3,
.v3-section-head h3 {
  margin: 0 0 4px;
}

.v3-primary-answer-head p,
.v3-section-head p {
  margin: 0;
}

.v3-key-findings {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.v3-outcome-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.v3-outcome-card {
  display: grid;
  gap: 6px;
  padding: 14px;
  border: 1px solid rgba(79, 70, 229, 0.12);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.86);
  box-shadow: 0 1px 2px rgba(15, 20, 25, 0.03);
}

.v3-outcome-card span {
  font-size: 0.74rem;
  font-weight: 800;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--text-muted, #8b929e);
}

.v3-outcome-card strong {
  font-size: 0.96rem;
  color: var(--text-primary, #1a1d26);
  line-height: 1.45;
}

.v3-outcome-card small {
  color: var(--text-secondary, #5c6370);
  line-height: 1.45;
}

.v3-flow-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(300px, 0.85fr);
  gap: 16px;
  align-items: start;
}

.v3-run-title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.v3-run-title h3 {
  margin: 0;
  font-size: 1.1rem;
  line-height: 1.4;
}

.v3-run-badges {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.08);
  color: var(--text-secondary, #475569);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.status-badge {
  padding: 4px 12px;
  font-size: 0.78rem;
}

.badge-ok {
  background: rgba(16, 185, 129, 0.12);
  color: #047857;
}

.badge-bad {
  background: rgba(220, 38, 38, 0.12);
  color: #b91c1c;
}

.badge-warn {
  background: rgba(245, 158, 11, 0.12);
  color: #b45309;
}

.badge-muted {
  background: rgba(100, 116, 139, 0.1);
  color: #64748b;
}

.v3-run-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 0.82rem;
  color: var(--text-secondary, #5c6370);
}

.v3-meta-item strong {
  color: var(--text-primary, #1a1d26);
}

.v3-flow-chain {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.v3-flow-node {
  appearance: none;
  width: 100%;
  text-align: left;
  cursor: pointer;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid var(--border-subtle, rgba(15, 20, 25, 0.08));
  background: #fff;
}

.v3-flow-node.is-selected {
  border-color: rgba(79, 70, 229, 0.34);
  box-shadow: 0 8px 22px rgba(79, 70, 229, 0.12);
  transform: translateY(-1px);
}

.v3-flow-node.is-completed {
  border-color: rgba(16, 185, 129, 0.3);
  background: rgba(16, 185, 129, 0.04);
}

.v3-flow-node.is-failed {
  border-color: rgba(220, 38, 38, 0.4);
  background: rgba(220, 38, 38, 0.06);
}

.v3-flow-node.is-partial_completed {
  border-color: rgba(245, 158, 11, 0.35);
  background: rgba(245, 158, 11, 0.06);
}

.v3-flow-node-index {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--text-muted, #8b929e);
  flex-shrink: 0;
  padding-top: 2px;
}

.v3-flow-node-content {
  flex: 1;
  min-width: 0;
}

.v3-flow-node-title {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 4px;
}

.v3-flow-node-title strong {
  font-size: 0.9rem;
}

.v3-flow-node-id {
  font-size: 0.72rem;
  color: var(--text-muted, #8b929e);
  font-family: var(--mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace);
}

.v3-flow-node-summary {
  font-size: 0.82rem;
  line-height: 1.5;
  color: var(--text-secondary, #5c6370);
}

.v3-flow-node-status {
  flex-shrink: 0;
  font-size: 0.75rem;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(100, 116, 139, 0.1);
  color: #64748b;
}

.v3-flow-node.is-completed .v3-flow-node-status {
  background: rgba(16, 185, 129, 0.12);
  color: #047857;
}

.v3-flow-node.is-failed .v3-flow-node-status {
  background: rgba(220, 38, 38, 0.12);
  color: #b91c1c;
}

.v3-flow-detail {
  padding: 14px;
  position: sticky;
  top: 12px;
}

.v3-flow-detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.v3-flow-detail-head h4 {
  margin: 0;
}

.v3-flow-detail-meta {
  display: grid;
  gap: 6px;
  margin-bottom: 12px;
}

.v3-flow-detail-meta p {
  margin: 0;
  color: var(--text-secondary, #5c6370);
  font-size: 0.84rem;
}

.v3-final-answer {
  line-height: 1.7;
  font-size: 0.92rem;
  color: var(--text-primary, #111827);
  padding: 16px;
  border-radius: 12px;
  background: rgba(79, 70, 229, 0.04);
  border: 1px solid rgba(79, 70, 229, 0.12);
}

.v3-final-answer-prominent {
  padding: 18px 20px;
  border-radius: 18px;
  background:
    radial-gradient(circle at top right, rgba(79, 70, 229, 0.08), transparent 34%),
    rgba(248, 250, 252, 0.88);
}

.v3-final-answer h1,
.v3-final-answer h2,
.v3-final-answer h3 {
  margin: 1em 0 0.5em;
  font-weight: 600;
}

.v3-final-answer h1 {
  font-size: 1.2rem;
}

.v3-final-answer h2 {
  font-size: 1.1rem;
}

.v3-final-answer h3 {
  font-size: 1rem;
  color: var(--accent-text, #4f46e5);
}

.v3-final-answer code {
  background: rgba(0, 0, 0, 0.05);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.85em;
  font-family: var(--mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace);
}

.v3-final-answer strong {
  font-weight: 600;
}

.v3-final-answer li {
  margin-left: 1.2em;
  list-style: disc;
}

.v3-final-answer p {
  margin: 0.5em 0;
}

.analysis-summary-content {
  line-height: 1.7;
  font-size: 0.9rem;
  color: var(--text-primary);
  padding: 16px;
  border-radius: 12px;
  background: rgba(79, 70, 229, 0.04);
  border: 1px solid rgba(79, 70, 229, 0.12);
}

.analysis-summary-content h1,
.analysis-summary-content h2,
.analysis-summary-content h3 {
  margin: 1em 0 0.5em;
  font-weight: 600;
}

.analysis-summary-content h1 {
  font-size: 1.2rem;
}

.analysis-summary-content h2 {
  font-size: 1.1rem;
}

.analysis-summary-content h3 {
  font-size: 1rem;
  color: var(--accent-text, #4f46e5);
}

.analysis-summary-content code {
  background: rgba(0, 0, 0, 0.05);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.85em;
  font-family: var(--mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace);
}

.analysis-summary-content strong {
  font-weight: 600;
}

.analysis-summary-content li {
  margin-left: 1.2em;
  list-style: disc;
}

.analysis-summary-content p {
  margin: 0.5em 0;
}

@media (max-width: 960px) {
  .v3-overview-grid,
  .v3-outcome-grid,
  .v3-key-findings,
  .v3-flow-layout {
    grid-template-columns: 1fr;
  }

  .v3-flow-detail {
    position: static;
  }
}

.v3-audit-summary {
  margin-bottom: 16px;
  padding: 12px;
  border-radius: 12px;
  background: rgba(79, 70, 229, 0.04);
  border: 1px solid rgba(79, 70, 229, 0.12);
}

.v3-audit-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.v3-audit-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.v3-audit-stat strong {
  font-size: 1.2rem;
  color: var(--text-primary, #111827);
}

.v3-audit-stat .muted {
  font-size: 0.75rem;
  margin-top: 2px;
}

.v3-audit-section {
  margin-top: 16px;
}

.v3-audit-section h4 {
  margin-bottom: 8px;
  font-size: 0.9rem;
  color: var(--text-primary, #111827);
}

.badge-enabled {
  background: rgba(16, 185, 129, 0.12);
  color: #047857;
}

.badge-disabled {
  background: rgba(100, 116, 139, 0.1);
  color: #64748b;
}

@media (max-width: 640px) {
  .v3-audit-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

</style>
