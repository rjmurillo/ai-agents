# Agent Invocation Metrics

## Purpose

This document defines the 8 key metrics for measuring agent system health, effectiveness, and adoption. These metrics enable data-driven decisions about agent system evolution.

## The 8 Key Metrics

### Metric 1: Invocation Rate by Agent

**Description**: How often each agent is used relative to others.

**Formula**:

```text
Invocation Rate = (Agent invocations) / (Total all agent invocations) * 100
```

**Measurement Method**:

- Parse commit messages for agent references
- Parse PR descriptions for agent mentions
- Track orchestrator routing decisions

**Targets**:

| Agent Type | Target Rate |
|------------|-------------|
| Orchestrator | 80%+ of multi-domain tasks |
| Security | 100% of security-critical changes |
| Other agents | Proportional to task type distribution |

**Dashboard Display**: Pie chart showing distribution.

---

### Metric 2: Agent Coverage

**Description**: Percentage of commits that involved agent review.

**Formula**:

```text
Coverage = (Commits with agent reference) / (Total commits) * 100
```

**Measurement Method**:

- Search commit messages for agent patterns
- Check PR descriptions for agent review sections
- Review conventional commit tags

**Detection Patterns**:

```regex
# Commit message patterns
(?i)(security agent|architect agent|implementer agent)
(?i)reviewed by:?\s*(security|architect|analyst)
(?i)agent:\s*\w+
```

**Targets**:

| Code Type | Target Coverage |
|-----------|-----------------|
| All commits | 50% baseline |
| Security-critical | 100% |
| Multi-domain changes | 90% |

---

### Metric 3: Shift-Left Effectiveness

**Description**: Issues caught during agent review vs. PR review vs. production.

**Formula**:

```text
Shift-Left % = (Issues caught by agents) / (Total issues) * 100
```

**Issue Categories**:

| Category | When Caught | Target |
|----------|-------------|--------|
| Pre-implementation | Agent review | 80% |
| PR review | Bot/human review | 15% |
| Production | Incident | 5% |

**Measurement Method**:

- Track issues tagged with "caught-by-agent"
- Track PR review comments requiring changes
- Track production incidents

**Current Baseline**: 0% (CWE-78 incident caught in PR review, not pre-impl)

---

### Metric 4: Infrastructure Code Review Rate

**Description**: Percentage of infrastructure changes that received security agent review.

**Formula**:

```text
Review Rate = (Infra commits with security review) / (Total infra commits) * 100
```

**Infrastructure Patterns**:

```text
.github/workflows/*
.githooks/*
build/scripts/*
Dockerfile*
docker-compose*
*.tf, *.tfvars
```

**Measurement Method**:

- Identify commits touching infrastructure patterns
- Check for security agent reference
- Use security detection utility output

**Targets**:

| Metric | Baseline | Target |
|--------|----------|--------|
| Review rate | 0% (pre-Issue #9) | 100% |
| Alert compliance | N/A | 90% response to warnings |

---

### Metric 5: Usage Distribution by Agent

**Description**: Which agents are most/least utilized.

**Purpose**:

- Identify underutilized agents (consolidation candidates)
- Identify overworked agents (specialization candidates)
- Validate routing algorithm effectiveness

**Display**: Monthly trend chart per agent.

**Analysis Triggers**:

| Observation | Action |
|-------------|--------|
| Agent < 5% usage for 3 months | Review for consolidation |
| Agent > 30% usage | Review for specialization |
| Usage spike | Investigate cause |

---

### Metric 6: Agent Review Turnaround Time

**Description**: How long agent review takes.

**Formula**:

```text
Turnaround = (Review completion time) - (Review request time)
```

**Measurement Method**:

- Manual tracking via timestamps in agent output
- PR timeline analysis
- Session duration analysis

**Targets**:

| Review Type | Target Time |
|-------------|-------------|
| Quick review (single file) | < 5 minutes |
| Standard review | < 30 minutes |
| Comprehensive review | < 2 hours |

**ROI Analysis**:

```text
Value = (Time saved from caught issues) - (Review turnaround time)
```

---

### Metric 7: Vulnerability Discovery Timeline

**Description**: When security issues are discovered in the development lifecycle.

**Categories**:

| Phase | Definition | Target % |
|-------|------------|----------|
| Agent review | Caught during pre-implementation agent review | 80% |
| PR review | Caught during PR review (bot or human) | 15% |
| Production | Discovered in production/incident | 5% |

**Measurement Method**:

- Tag security issues with discovery phase
- Review incident reports
- Analyze PR review comments

**Current State**:

- CWE-78 incident: Discovered in PR review (0% agent, 100% PR)
- Target: 80% agent, 20% PR, 0% production

---

### Metric 8: Compliance with Agent Policies

**Description**: Are agent usage policies being followed?

**Policies Tracked**:

| Policy | Measurement |
|--------|-------------|
| Orchestrator for multi-domain | % of multi-domain tasks using orchestrator |
| Security for infrastructure | % of infra changes with security review |
| QA after implementation | % of implementer outputs followed by QA |
| Conventional commits | % of commits following conventions |

**Targets**:

| Policy | Target Compliance |
|--------|-------------------|
| Orchestrator usage | 80% |
| Security review | 100% for critical, 80% for high |
| QA validation | 90% |
| Commit conventions | 100% |

---

## Measurement Implementation

### Data Collection

#### Commit Analysis

```bash
# Count commits with agent references
git log --oneline --grep="agent" | wc -l

# Count infrastructure commits
git log --oneline -- ".github/workflows/*" ".githooks/*" | wc -l
```

#### PR Analysis

```bash
# List PRs with security review checked
gh pr list --json title,body | jq '.[] | select(.body | contains("Security agent"))'
```

### Collection Schedule

| Metric | Collection Frequency | Aggregation |
|--------|---------------------|-------------|
| Invocation rate | Per commit | Weekly |
| Coverage | Per commit | Weekly |
| Shift-left | Per issue | Monthly |
| Infrastructure review | Per commit | Weekly |
| Usage distribution | Per session | Monthly |
| Turnaround time | Per review | Weekly |
| Vulnerability timeline | Per security issue | Monthly |
| Policy compliance | Per task | Weekly |

---

## Dashboard Template

See: `.agents/metrics/dashboard-template.md`

## Baseline Report

See: `.agents/metrics/baseline-report.md`

## CI Integration

See: `.github/workflows/agent-metrics.yml`

---

## Related Documents

- [Dashboard Template](../.agents/metrics/dashboard-template.md)
- [Baseline Report](../.agents/metrics/baseline-report.md)
- [Orchestrator Routing Algorithm](./orchestrator-routing-algorithm.md)
- [Agent Governance](./agent-governance.md)

---

*Document Version: 1.0*
*Created: 2025-12-13*
*GitHub Issue: #7*
