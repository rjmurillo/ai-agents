# Agent Metrics Dashboard

## Report Period

**From**: [Start Date]
**To**: [End Date]
**Generated**: [Generation Date]

---

## Executive Summary

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Agent Coverage | [X]% | 50% | [On Track/Behind] |
| Shift-Left Effectiveness | [X]% | 80% | [On Track/Behind] |
| Infrastructure Review Rate | [X]% | 100% | [On Track/Behind] |
| Policy Compliance | [X]% | 90% | [On Track/Behind] |

---

## Metric 1: Invocation Rate by Agent

### Distribution

| Agent | Invocations | Rate | Trend |
|-------|-------------|------|-------|
| orchestrator | [N] | [X]% | [up/down/stable] |
| analyst | [N] | [X]% | [up/down/stable] |
| architect | [N] | [X]% | [up/down/stable] |
| implementer | [N] | [X]% | [up/down/stable] |
| security | [N] | [X]% | [up/down/stable] |
| qa | [N] | [X]% | [up/down/stable] |
| devops | [N] | [X]% | [up/down/stable] |
| critic | [N] | [X]% | [up/down/stable] |
| milestone-planner | [N] | [X]% | [up/down/stable] |
| Other | [N] | [X]% | [up/down/stable] |
| **Total** | **[N]** | **100%** | - |

### Observations

- [Observation about distribution]
- [Notable changes from previous period]

---

## Metric 2: Agent Coverage

### Coverage by Commit Type

| Commit Type | Commits | With Agent | Coverage |
|-------------|---------|------------|----------|
| Feature | [N] | [N] | [X]% |
| Bug fix | [N] | [N] | [X]% |
| Infrastructure | [N] | [N] | [X]% |
| Documentation | [N] | [N] | [X]% |
| Refactoring | [N] | [N] | [X]% |
| **Total** | **[N]** | **[N]** | **[X]%** |

### Trend

| Period | Coverage |
|--------|----------|
| [Month-3] | [X]% |
| [Month-2] | [X]% |
| [Month-1] | [X]% |
| Current | [X]% |

---

## Metric 3: Shift-Left Effectiveness

### Issue Discovery Phase

| Phase | Issues | Percentage | Target |
|-------|--------|------------|--------|
| Agent review | [N] | [X]% | 80% |
| PR review | [N] | [X]% | 15% |
| Production | [N] | [X]% | 5% |
| **Total** | **[N]** | **100%** | - |

### Shift-Left Score

```text
Score = Agent % + (PR % * 0.5) + (Production % * 0)
Current Score: [X]
Target Score: 87.5 (80 + 7.5 + 0)
```

---

## Metric 4: Infrastructure Code Review Rate

### Infrastructure Changes

| Pattern | Commits | Reviewed | Rate |
|---------|---------|----------|------|
| `.github/workflows/*` | [N] | [N] | [X]% |
| `.githooks/*` | [N] | [N] | [X]% |
| `Dockerfile*` | [N] | [N] | [X]% |
| `*.tf` | [N] | [N] | [X]% |
| Other infra | [N] | [N] | [X]% |
| **Total** | **[N]** | **[N]** | **[X]%** |

### Alert Response

| Alerts Shown | Followed | Ignored | Response Rate |
|--------------|----------|---------|---------------|
| [N] | [N] | [N] | [X]% |

---

## Metric 5: Usage Distribution

### Monthly Trend

| Agent | Month-3 | Month-2 | Month-1 | Current | Trend |
|-------|---------|---------|---------|---------|-------|
| orchestrator | [X]% | [X]% | [X]% | [X]% | [arrow] |
| security | [X]% | [X]% | [X]% | [X]% | [arrow] |
| implementer | [X]% | [X]% | [X]% | [X]% | [arrow] |
| analyst | [X]% | [X]% | [X]% | [X]% | [arrow] |

### Anomalies

- [Agents with significant changes]
- [Consolidation candidates (< 5%)]
- [Specialization candidates (> 30%)]

---

## Metric 6: Agent Review Turnaround Time

### Average Turnaround

| Review Type | Average Time | Target | Status |
|-------------|--------------|--------|--------|
| Quick (single file) | [X] min | < 5 min | [Met/Not Met] |
| Standard | [X] min | < 30 min | [Met/Not Met] |
| Comprehensive | [X] min | < 120 min | [Met/Not Met] |

### ROI Analysis

| Metric | Value |
|--------|-------|
| Total review time | [X] hours |
| Issues caught | [N] |
| Estimated time saved | [X] hours |
| Net ROI | [+/-X] hours |

---

## Metric 7: Vulnerability Discovery Timeline

### Security Issue Discovery

| Discovery Phase | Count | Percentage |
|-----------------|-------|------------|
| Pre-implementation (Agent) | [N] | [X]% |
| PR Review | [N] | [X]% |
| Production | [N] | [X]% |

### Notable Incidents

| Incident | Discovery Phase | Severity | Resolution |
|----------|-----------------|----------|------------|
| [Description] | [Phase] | [Severity] | [Status] |

---

## Metric 8: Policy Compliance

### Compliance Rates

| Policy | Compliance | Target | Gap |
|--------|------------|--------|-----|
| Orchestrator for multi-domain | [X]% | 80% | [X]% |
| Security for infrastructure | [X]% | 100% | [X]% |
| QA after implementer | [X]% | 90% | [X]% |
| Conventional commits | [X]% | 100% | [X]% |

### Non-Compliance Details

| Policy | Violations | Common Reason |
|--------|------------|---------------|
| [Policy] | [N] | [Reason] |

---

## Recommendations

### Immediate Actions

1. [Action based on metrics]
2. [Action based on metrics]

### Process Improvements

1. [Improvement based on trends]
2. [Improvement based on trends]

### Consolidation Candidates

| Agent | Usage | Recommendation |
|-------|-------|----------------|
| [Agent] | [X]% | [Recommendation] |

---

## Data Sources

| Source | Collection Method | Frequency |
|--------|-------------------|-----------|
| Commits | Git log analysis | Daily |
| PRs | GitHub API | Daily |
| Issues | Issue tracker | Weekly |
| Incidents | Incident reports | Monthly |

---

*Dashboard Template Version: 1.0*
*GitHub Issue: #7*
