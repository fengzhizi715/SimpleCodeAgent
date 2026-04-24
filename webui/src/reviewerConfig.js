export const REVIEWER_CONFIG_STORAGE_KEY = "simple-code-agent:v2-reviewer-strategy";

export const defaultReviewRuleGroups = ["scope", "testing", "security", "maintainability", "boundaries", "api", "domain"];

export const defaultReviewStrategy = {
  llm_enabled: true,
  strictness: "normal",
  max_issues: 5,
  focus_areas: [],
  rule_groups: [...defaultReviewRuleGroups],
  test_failure_mode: "block",
};

export const reviewRuleGroups = [
  { id: "scope", label: "Scope", help: "改动范围、删除文件、未落盘风险" },
  { id: "testing", label: "Testing", help: "缺少测试、测试失败、验证缺口" },
  { id: "security", label: "Security", help: "eval、shell、密钥、路径穿越" },
  { id: "maintainability", label: "Maintainability", help: "宽泛异常、TODO、一般可维护性" },
  { id: "boundaries", label: "Boundaries", help: "v1/v2 边界和共享 contract 风险" },
  { id: "api", label: "API", help: "公共函数、类、导出接口变更" },
  { id: "domain", label: "Domain", help: "认证、存储、数据库路径" },
];

export function normalizeReviewStrategy(input = {}) {
  const raw = input && typeof input === "object" ? input : {};
  const strictness = ["light", "normal", "strict"].includes(raw.strictness) ? raw.strictness : "normal";
  const testFailureMode = ["off", "suggest", "block"].includes(raw.test_failure_mode)
    ? raw.test_failure_mode
    : "block";
  const rawGroups = Array.isArray(raw.rule_groups) ? raw.rule_groups : defaultReviewRuleGroups;
  const ruleGroups = defaultReviewRuleGroups.filter((group) => rawGroups.includes(group));
  const rawFocusAreas = Array.isArray(raw.focus_areas) ? raw.focus_areas : [];

  return {
    llm_enabled: typeof raw.llm_enabled === "boolean" ? raw.llm_enabled : true,
    strictness,
    max_issues: Math.min(Math.max(Number(raw.max_issues) || 5, 1), 10),
    focus_areas: rawFocusAreas.map((item) => String(item).trim()).filter(Boolean).slice(0, 8),
    rule_groups: ruleGroups.length ? ruleGroups : [...defaultReviewRuleGroups],
    test_failure_mode: testFailureMode,
  };
}

export function loadReviewStrategy() {
  if (typeof window === "undefined") {
    return normalizeReviewStrategy(defaultReviewStrategy);
  }
  try {
    const raw = window.localStorage.getItem(REVIEWER_CONFIG_STORAGE_KEY);
    if (!raw) {
      return normalizeReviewStrategy(defaultReviewStrategy);
    }
    return normalizeReviewStrategy(JSON.parse(raw));
  } catch {
    return normalizeReviewStrategy(defaultReviewStrategy);
  }
}

export function saveReviewStrategy(strategy) {
  const normalized = normalizeReviewStrategy(strategy);
  if (typeof window !== "undefined") {
    window.localStorage.setItem(REVIEWER_CONFIG_STORAGE_KEY, JSON.stringify(normalized));
  }
  return normalized;
}

export function resetReviewStrategy() {
  const normalized = normalizeReviewStrategy(defaultReviewStrategy);
  if (typeof window !== "undefined") {
    window.localStorage.setItem(REVIEWER_CONFIG_STORAGE_KEY, JSON.stringify(normalized));
  }
  return normalized;
}
