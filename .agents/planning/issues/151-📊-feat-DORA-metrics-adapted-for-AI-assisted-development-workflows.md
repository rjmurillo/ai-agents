---
number: 151
title: "📊 feat: DORA metrics adapted for AI-assisted development workflows"
state: OPEN
created_at: 12/20/2025 09:38:40
author: rjmurillo-bot
labels: ["enhancement", "area-workflows", "priority:P2", "automation", "metrics"]
assignees: []
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/151
---

# 📊 feat: DORA metrics adapted for AI-assisted development workflows

## 📊 Summary

Implement DORA (DevOps Research and Assessment) metrics adapted for AI-assisted development workflows. Track velocity, quality, and agent effectiveness to measure development acceleration.

**Mission**: Data-driven velocity insights 📈

## Background: What are DORA Metrics?

The four key DORA metrics for elite DevOps teams:

| Metric | Description | Elite Target |
|--------|-------------|--------------|
| **Deployment Frequency** | How often code ships | On-demand (multiple/day) |
| **Lead Time for Changes** | Commit to production | <1 hour |
| **Change Failure Rate** | Deployments causing failures | <15% |
| **Mean Time to Recovery** | Time to recover from failure | <1 hour |

## Adapted Metrics for AI Agents Repository

For a repository focused on AI agent development workflows, we adapt DORA metrics to:

### 1. Issue-to-PR Velocity (Lead Time)
```
Time from issue creation → first PR addressing it
Target: <4 hours (P0/P1), <24 hours (P2)
```

### 2. PR Lead Time (Time to Merge)
```
Time from PR creation → merge
Target: <6 hours (simple), <24 hours (complex)
```

### 3. Review Cycle Rate (Quality)
```
Number of review cycles before merge
Target: <2 cycles average
```

### 4. PR Success Rate (Quality)
```
% of PRs that merge successfully vs. closed without merge
Target: >90%
```

### 5. Agent Effectiveness (AI-specific)
```
% of agent-assisted PRs that merge on first attempt
Target: >75%
```

### 6. Agent Utilization (AI-specific)
```
% of issues with agent involvement
Target: >80%
```

## Existing Pieces We Can Leverage

We already have components that can feed metrics:

| Component | Data Available | Metric |
|-----------|---------------|--------|
| AI Quality Gate workflow | Verdict per PR | Change Failure Rate |
| Copilot assignment | Issue → PR correlation | Issue-to-PR Velocity |
| PR review comments | Review cycles count | Review Cycle Rate |
| Session logs | Agent involvement | Agent Utilization |
| GitHub Actions history | Workflow success/failure | Recovery Time |

## Implementation Proposal

### Phase 1: Data Collection
Create a metrics collection script that queries:
- GitHub API for PR/Issue timeline data
- Workflow run history for success/failure rates
- Session logs for agent involvement

### Phase 2: Metrics Calculation
PowerShell module: `.github/scripts/DORAMetrics.psm1`

```powershell
function Get-DORAMetrics {
    param(
        [DateTime]$StartDate = (Get-Date).AddDays(-30),
        [DateTime]$EndDate = (Get-Date)
    )

    return @{
        IssueToePRVelocity = Get-IssueVelocity -Start $StartDate -End $EndDate
        PRLeadTime = Get-PRLeadTime -Start $StartDate -End $EndDate
        ReviewCycleRate = Get-ReviewCycles -Start $StartDate -End $EndDate
        PRSuccessRate = Get-PRSuccessRate -Start $StartDate -End $EndDate
        AgentEffectiveness = Get-AgentEffectiveness -Start $StartDate -End $EndDate
        AgentUtilization = Get-AgentUtilization -Start $StartDate -End $EndDate
    }
}
```

### Phase 3: Dashboard/Reporting
- Store metrics in `.agents/metrics/` directory
- Weekly summary workflow (cron job)
- Trend visualization (markdown tables + optional charts)

### Phase 4: Velocity Insights
Integrate with Issue #148 (Velocity Accelerator):
- Use metrics to identify bottlenecks
- Auto-prioritize based on velocity impact
- Detect stalled items that hurt metrics

## Metrics Storage Format

```yaml
# .agents/metrics/2025-12-20.yml
date: 2025-12-20
period: daily
metrics:
  issue_to_pr_velocity:
    count: 5
    avg_hours: 3.2
    p95_hours: 8.0
  pr_lead_time:
    count: 8
    avg_hours: 12.5
    p95_hours: 24.0
  review_cycle_rate:
    avg_cycles: 1.5
    multi_cycle_pct: 25.0
  pr_success_rate: 92.5
  agent_effectiveness: 78.0
  agent_utilization: 85.0
```

## Success Metrics (Meta!)

| Metric | Baseline | Target (30 days) |
|--------|----------|------------------|
| Issue-to-PR Velocity | TBD | <4 hours |
| PR Lead Time | TBD | <12 hours |
| Review Cycle Rate | TBD | <2 cycles |
| Agent Utilization | TBD | >80% |

## Acceptance Criteria

- [ ] `Get-DORAMetrics` function implemented
- [ ] Data collection queries GitHub API correctly
- [ ] Metrics stored in `.agents/metrics/`
- [ ] Weekly cron job generates summary
- [ ] Integration with Velocity Accelerator workflow
- [ ] Baseline established from historical data

## Related

- Issue #148: Velocity Accelerator workflow
- Existing: AI Quality Gate verdicts (change failure rate proxy)
- Existing: Session logs (agent involvement tracking)

## Research Questions

1. What's our current baseline for each metric?
2. Should we track per-agent effectiveness (analyst vs. implementer)?
3. How do we handle draft PRs in lead time calculations?
4. Should complexity-weighted metrics be included?

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)


---

## Comments

### Comment by @coderabbitai on 12/20/2025 09:40:16

<!-- This is an auto-generated issue plan by CodeRabbit -->


### 📝 CodeRabbit Plan Mode
Generate an implementation plan and prompts that you can use with your favorite coding agent.

- [ ] <!-- {"checkboxId": "8d4f2b9c-3e1a-4f7c-a9b2-d5e8f1c4a7b9"} --> Create Plan

<details>
<summary>Examples</summary>

- [Example 1](https://github.com/coderabbitai/git-worktree-runner/issues/29#issuecomment-3589134556)
- [Example 2](https://github.com/coderabbitai/git-worktree-runner/issues/12#issuecomment-3606665167)

</details>

---

<details>
<summary><b>🔗 Similar Issues</b></summary>

**Possible Duplicates**
- https://github.com/rjmurillo/ai-agents/issues/148

**Related Issues**
- https://github.com/rjmurillo/ai-agents/issues/108
- https://github.com/rjmurillo/ai-agents/issues/7
- https://github.com/rjmurillo/ai-agents/issues/116
</details>
<details>
<summary><b>🔗 Related PRs</b></summary>

rjmurillo/vs-code-agents#1 - feat: Add customized multi-agent system for VS Code and Claude Code [merged]
rjmurillo/vs-code-agents#3 - feat: add GitHub Copilot CLI support  [merged]
rjmurillo/ai-agents#23 - feat: enhance pr-comment-responder with memory patterns and agent routing [merged]
rjmurillo/ai-agents#60 - feat: AI-powered GitHub Actions workflows with security-hardened PowerShell implementation [merged]
rjmurillo/ai-agents#70 - feat(agents): add VS Code agent system [merged]
</details>
<details>
<summary><b>👤 Suggested Assignees</b></summary>

- [rjmurillo-bot](https://github.com/rjmurillo-bot)
- [rjmurillo](https://github.com/rjmurillo)
</details>


---
<details>
<summary> 🧪 Issue enrichment is currently in open beta.</summary>


You can configure auto-planning by selecting labels in the issue_enrichment configuration.

To disable automatic issue enrichment, add the following to your `.coderabbit.yaml`:
```yaml
issue_enrichment:
  auto_enrich:
    enabled: false
```
</details>

💬 Have feedback or questions? Drop into our [discord](https://discord.gg/coderabbit) or [schedule a call](https://calendly.com/parth-coderabbit/issues-feedback)!

### Comment by @github-actions on 12/20/2025 09:43:21

<!-- AI-PRD-GENERATION -->

## 📋 Product Requirements Document

> [!IMPORTANT]
> This PRD was automatically generated based on issue triage escalation.
> **Complexity Score**: 10/12 ()
> **Escalation Criteria**: feature_request, research_required, multi_phase_work, external_dependency

<details>
<summary>📖 About this PRD</summary>

This PRD was generated by the **Explainer Agent** after the issue was flagged
for detailed analysis. The document is designed to be self-contained - it can
be passed to a separate AI agent instance for implementation without additional
context.

**PRD Depth Levels**:
- **Standard** (4-6): Brief analysis, clear requirements
- **Detailed** (7-9): Research section, blocking questions
- **Comprehensive** (10-12): Phased implementation, risk analysis

</details>

---

Now I have a clear picture of the existing metrics infrastructure. Let me create the PRD.

The file creation failed. Let me output the PRD directly.

---

# PRD: DORA Metrics for AI-Assisted Development Workflows

## Executive Summary

This repository lacks velocity and quality metrics that measure development acceleration from AI agent assistance. The existing agent metrics system tracks agent invocation patterns but does not capture time-based workflow metrics essential for measuring delivery speed and quality.

| Scope | Status | Blocker |
|-------|--------|---------|
| Data Collection Module | :green_circle: READY | None |
| Metrics Calculation Engine | :green_circle: READY | None |
| Storage Format Implementation | :green_circle: READY | None |
| Weekly Cron Workflow | :green_circle: READY | None |
| Dashboard/Reporting | :green_circle: READY | None |
| Velocity Accelerator Integration | :yellow_circle: PARTIAL | Issue #148 not yet implemented |

**Verdict**: READY for implementation. Issue #148 integration can proceed as a follow-up task.

---

## Problem Statement

### Current State

| Component | Exists | Measures |
|-----------|--------|----------|
| `.agents/utilities/metrics/collect_metrics.py` | Yes | Agent invocation counts, coverage rates |
| `.agents/metrics/baseline-report.md` | Yes | Agent coverage, shift-left effectiveness |
| `.agents/metrics/dashboard-template.md` | Yes | Template for agent metrics display |
| `.github/workflows/agent-metrics.yml` | Yes | Weekly automated agent metrics collection |
| DORA/velocity metrics | No | N/A |

### Gap Analysis

The current metrics system answers "How often do agents participate?" but not:

1. **How fast do issues become PRs?** Issue-to-PR velocity not tracked.
2. **How quickly do PRs merge?** PR lead time not calculated.
3. **How efficient is the review process?** Review cycle count not measured.
4. **What is the PR success rate?** Merge vs. close ratio not captured.
5. **Are agent-assisted PRs more successful?** Agent effectiveness not compared.
6. **What percentage of work uses agents?** Agent utilization by issue not tracked.

### User Impact

| User | Impact |
|------|--------|
| Repository maintainers | Cannot identify bottlenecks in development workflow |
| AI agent developers | Cannot measure agent effectiveness on delivery speed |
| Contributors | No visibility into expected PR turnaround times |

---

## Research Findings

### DORA Metrics Background

**Source**: [DORA Research Program](https://dora.dev/research/)

**Confidence**: CONFIRMED

The four DORA metrics correlate with high-performing engineering organizations:

| Metric | Elite Target | High Target | Medium Target |
|--------|--------------|-------------|---------------|
| Deployment Frequency | On-demand (multiple/day) | Weekly-monthly | Monthly-quarterly |
| Lead Time for Changes | <1 hour | 1 day-1 week | 1 week-1 month |
| Change Failure Rate | <15% | 16-30% | 31-45% |
| Mean Time to Recovery | <1 hour | <1 day | 1 day-1 week |

### Adapted Metrics for This Repository

This repository focuses on AI agent development workflows, not production deployments. Adapted metrics:

| DORA Metric | Adapted Metric | Rationale |
|-------------|----------------|-----------|
| Deployment Frequency | Not applicable | No production deployments |
| Lead Time for Changes | Issue-to-PR Velocity, PR Lead Time | Measures idea-to-implementation speed |
| Change Failure Rate | PR Success Rate, Review Cycle Rate | Measures quality without deployments |
| Mean Time to Recovery | Not applicable | No production incidents |

### GitHub API Data Availability

**Confidence**: CONFIRMED

| Data Point | API Endpoint | Available Fields |
|------------|--------------|------------------|
| Issue creation time | `GET /repos/{owner}/{repo}/issues/{issue_number}` | `created_at` |
| PR creation time | `GET /repos/{owner}/{repo}/pulls/{pull_number}` | `created_at`, `merged_at`, `closed_at` |
| PR reviews | `GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews` | `submitted_at`, array length for cycle count |
| PR comments | `GET /repos/{owner}/{repo}/issues/{issue_number}/comments` | `created_at`, can filter by author |
| Issue-PR linkage | `GET /repos/{owner}/{repo}/pulls/{pull_number}` | `body` contains "Fixes #N" or "Closes #N" |

---

## Proposed Solution

### Phase 1: Data Collection Module (Status: READY)

**Estimated Effort**: M (2-4 hours)

**Blockers**: None

| Task | Description |
|------|-------------|
| 1.1 | Create `Get-IssueVelocity` function in PowerShell module |
| 1.2 | Create `Get-PRLeadTime` function |
| 1.3 | Create `Get-ReviewCycles` function |
| 1.4 | Create `Get-PRSuccessRate` function |
| 1.5 | Create `Get-AgentEffectiveness` function |
| 1.6 | Create `Get-AgentUtilization` function |

### Phase 2: Metrics Calculation Engine (Status: READY)

**Estimated Effort**: M (2-4 hours)

**Blockers**: None

**Depends On**: Phase 1

| Task | Description |
|------|-------------|
| 2.1 | Create `DORAMetrics.psm1` module at `.github/scripts/DORAMetrics.psm1` |
| 2.2 | Implement `Get-DORAMetrics` orchestration function |
| 2.3 | Add statistical calculations (avg, p95, percentiles) |
| 2.4 | Add trend comparison with previous period |

### Phase 3: Storage and Reporting (Status: READY)

**Estimated Effort**: S (1-2 hours)

**Blockers**: None

**Depends On**: Phase 2

| Task | Description |
|------|-------------|
| 3.1 | Define YAML schema for daily metrics at `.agents/metrics/YYYY-MM-DD.yml` |
| 3.2 | Create markdown report generator |
| 3.3 | Update `.agents/metrics/dashboard-template.md` with DORA sections |

### Phase 4: CI Integration (Status: READY)

**Estimated Effort**: S (1-2 hours)

**Blockers**: None

**Depends On**: Phase 3

| Task | Description |
|------|-------------|
| 4.1 | Create `.github/workflows/dora-metrics.yml` with weekly cron |
| 4.2 | Add workflow dispatch inputs for date range |
| 4.3 | Configure artifact upload for metrics reports |

### Phase 5: Velocity Accelerator Integration (Status: PARTIAL)

**Estimated Effort**: L (4-8 hours)

**Blockers**: Issue #148 not yet implemented

**Depends On**: Phase 4, Issue #148 completion

| Task | Description |
|------|-------------|
| 5.1 | Integrate bottleneck detection from DORA metrics |
| 5.2 | Auto-prioritize issues based on velocity impact |
| 5.3 | Alert on stalled items affecting metrics |

---

## Functional Requirements

### FR-1: Issue-to-PR Velocity

**Priority**: P0

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-1.1 | Calculate time from issue creation to first linked PR creation | Returns hours as float, handles issues with no PR |
| FR-1.2 | Support filtering by issue labels (P0, P1, P2) | Accepts label filter parameter |
| FR-1.3 | Calculate average and P95 for reporting period | Returns both values in output |

### FR-2: PR Lead Time

**Priority**: P0

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-2.1 | Calculate time from PR creation to merge | Returns hours, excludes unmerged PRs |
| FR-2.2 | Exclude draft PRs from calculation | Draft PRs filtered by default, toggle parameter |
| FR-2.3 | Categorize by complexity (simple/complex) | Uses label or file count heuristic |

### FR-3: Review Cycle Rate

**Priority**: P1

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-3.1 | Count review cycles per PR | Review cycle = request changes + re-approval |
| FR-3.2 | Calculate average cycles for period | Returns float average |
| FR-3.3 | Track multi-cycle percentage | Returns % of PRs with >1 cycle |

### FR-4: PR Success Rate

**Priority**: P1

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-4.1 | Calculate merged PRs / total closed PRs | Returns percentage |
| FR-4.2 | Exclude bot-created PRs (Dependabot) | Filter by author pattern |
| FR-4.3 | Track by time period (weekly, monthly) | Configurable date range |

### FR-5: Agent Effectiveness

**Priority**: P0

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-5.1 | Identify agent-assisted PRs from session logs | Parse `.agents/sessions/` for PR references |
| FR-5.2 | Calculate first-attempt merge rate for agent PRs | Returns percentage |
| FR-5.3 | Compare to non-agent PR success rate | Returns delta value |

### FR-6: Agent Utilization

**Priority**: P1

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-6.1 | Track issues with agent involvement | Parse issue comments, PR descriptions |
| FR-6.2 | Calculate percentage of total issues | Returns percentage |
| FR-6.3 | Track by agent type | Returns breakdown by agent name |

---

## Non-Functional Requirements

### Consistency

- Use PowerShell for new metrics module (matches existing `.github/scripts/` patterns)
- Follow function naming convention: `Get-{MetricName}`
- Export module functions explicitly with `Export-ModuleMember`
- Use `gh` CLI for GitHub API calls (no raw API calls)

### Testability

- Create Pester tests in `.github/scripts/DORAMetrics.Tests.ps1`
- Mock `gh` CLI calls in unit tests
- Test edge cases: no PRs, no issues, API rate limits

### Documentation

- Update `.agents/metrics/SKILL.md` with DORA metrics usage
- Add examples to module help comments
- Document YAML schema in dedicated file

---

## Technical Design

### DORAMetrics.psm1 Structure

```powershell
# .github/scripts/DORAMetrics.psm1

#Requires -Version 7.0

function Get-IssueVelocity {
    [CmdletBinding()]
    param(
        [DateTime]$StartDate = (Get-Date).AddDays(-30),
        [DateTime]$EndDate = (Get-Date),
        [string[]]$Labels = @()
    )

    $issues = gh issue list --state all --json number,createdAt,labels --limit 500 |
        ConvertFrom-Json

    foreach ($issue in $issues) {
        $linkedPRs = gh pr list --search "fixes #$($issue.number)" --json number,createdAt |
            ConvertFrom-Json
    }

    return @{
        count = $issues.Count
        avg_hours = [math]::Round($totalHours / $count, 1)
        p95_hours = Get-Percentile -Values $hoursList -Percentile 95
    }
}

function Get-PRLeadTime {
    [CmdletBinding()]
    param(
        [DateTime]$StartDate = (Get-Date).AddDays(-30),
        [DateTime]$EndDate = (Get-Date),
        [switch]$IncludeDrafts
    )

    $prs = gh pr list --state merged --json number,createdAt,mergedAt --limit 500 |
        ConvertFrom-Json

    return @{
        count = $prs.Count
        avg_hours = [math]::Round($totalHours / $count, 1)
        p95_hours = Get-Percentile -Values $hoursList -Percentile 95
    }
}

function Get-DORAMetrics {
    [CmdletBinding()]
    param(
        [DateTime]$StartDate = (Get-Date).AddDays(-30),
        [DateTime]$EndDate = (Get-Date)
    )

    return @{
        IssueToePRVelocity = Get-IssueVelocity -Start $StartDate -End $EndDate
        PRLeadTime = Get-PRLeadTime -Start $StartDate -End $EndDate
        ReviewCycleRate = Get-ReviewCycles -Start $StartDate -End $EndDate
        PRSuccessRate = Get-PRSuccessRate -Start $StartDate -End $EndDate
        AgentEffectiveness = Get-AgentEffectiveness -Start $StartDate -End $EndDate
        AgentUtilization = Get-AgentUtilization -Start $StartDate -End $EndDate
    }
}

Export-ModuleMember -Function @(
    'Get-IssueVelocity'
    'Get-PRLeadTime'
    'Get-ReviewCycles'
    'Get-PRSuccessRate'
    'Get-AgentEffectiveness'
    'Get-AgentUtilization'
    'Get-DORAMetrics'
)
```

### Metrics Storage Schema

```yaml
# .agents/metrics/2025-12-20.yml
date: 2025-12-20
period: daily
metrics:
  issue_to_pr_velocity:
    count: 5
    avg_hours: 3.2
    p95_hours: 8.0
  pr_lead_time:
    count: 8
    avg_hours: 12.5
    p95_hours: 24.0
  review_cycle_rate:
    avg_cycles: 1.5
    multi_cycle_pct: 25.0
  pr_success_rate: 92.5
  agent_effectiveness: 78.0
  agent_utilization: 85.0
```

### Workflow Configuration

```yaml
# .github/workflows/dora-metrics.yml
name: DORA Metrics

on:
  schedule:
    - cron: '0 0 * * 0'
  workflow_dispatch:
    inputs:
      days:
        description: 'Number of days to analyze'
        default: '7'
        type: string

permissions:
  contents: read
  issues: read
  pull-requests: read

jobs:
  collect-dora-metrics:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Collect DORA Metrics
        shell: pwsh
        run: |
          Import-Module .github/scripts/DORAMetrics.psm1
          $metrics = Get-DORAMetrics -StartDate (Get-Date).AddDays(-${{ inputs.days || 7 }})
          $metrics | ConvertTo-Yaml | Out-File ".agents/metrics/$(Get-Date -Format 'yyyy-MM-dd').yml"
```

---

## Implementation Plan

### Prerequisites

- [x] Existing `.github/scripts/` directory structure
- [x] Existing `.agents/metrics/` directory
- [x] Existing `agent-metrics.yml` workflow pattern
- [x] GitHub CLI (`gh`) available in workflows

### Decision Tree

```text
Is PowerShell 7.0 available?
├── YES → Proceed to Phase 1
└── NO → Install PowerShell Core first (blocking)

Is GITHUB_TOKEN available?
├── YES → Use gh CLI for API calls
└── NO → Add to workflow secrets (blocking)

Does Issue #148 exist?
├── YES → Include Phase 5 integration
└── NO → Defer Phase 5 to follow-up
```

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| GitHub API rate limits | Medium | Medium | Use GraphQL batching, cache results |
| No linked PRs for issues | High | Low | Handle gracefully, report "N/A" for unlinked |
| Session log parsing fragile | Medium | Medium | Define stable patterns, use regex with fallbacks |
| Large repository history | Low | Medium | Limit date range, paginate API calls |
| Draft PR handling inconsistent | Medium | Low | Add toggle parameter, document default behavior |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| DORA metrics collection runs weekly without errors | 100% success rate |
| Issue-to-PR velocity tracked for >80% of issues | >80% coverage |
| PR lead time calculated for all merged PRs | 100% coverage |
| Agent effectiveness comparison available | Delta value reported |
| Baseline established within 30 days | Baseline document created |

---

## Open Questions (Non-Blocking)

1. **Q**: Should we track per-agent effectiveness (analyst vs. implementer)?
   - **Hypothesis**: Yes, valuable for identifying which agents accelerate delivery
   - **Status**: Implement as optional breakdown in `Get-AgentEffectiveness`

2. **Q**: How do we handle draft PRs in lead time calculations?
   - **Hypothesis**: Exclude by default, add `-IncludeDrafts` switch
   - **Status**: Document behavior, make configurable

3. **Q**: Should complexity-weighted metrics be included?
   - **Hypothesis**: Use file count or label-based complexity as proxy
   - **Status**: Add as optional parameter in Phase 2

4. **Q**: What is the current baseline for each metric?
   - **Hypothesis**: Unknown until first collection run
   - **Status**: Generate baseline report after Phase 4 completion

---

## Appendices

### Appendix A: Research Sources

| Source | URL | Date Accessed |
|--------|-----|---------------|
| DORA Research | https://dora.dev/research/ | 2025-12-20 |
| GitHub REST API | https://docs.github.com/en/rest | 2025-12-20 |
| Existing agent-metrics.yml | `.github/workflows/agent-metrics.yml` | Local |

### Appendix B: Existing Infrastructure

| File | Purpose |
|------|---------|
| `.agents/utilities/metrics/collect_metrics.py` | Agent invocation metrics (Python) |
| `.agents/utilities/metrics/SKILL.md` | Metrics utility documentation |
| `.agents/metrics/baseline-report.md` | Initial agent metrics baseline |
| `.agents/metrics/dashboard-template.md` | Metrics dashboard template |
| `.github/workflows/agent-metrics.yml` | Weekly agent metrics workflow |
| `.github/scripts/AIReviewCommon.psm1` | Common PowerShell functions |

### Appendix C: Related Issues

| Issue | Title | Relationship |
|-------|-------|--------------|
| #148 | Velocity Accelerator workflow | Integration target for Phase 5 |
| #7 | Agent Metrics | Original agent metrics implementation |

---

*PRD Version: 1.0*
*Created: 2025-12-20*
*Author: explainer agent*

---

<sub>📋 Generated by [AI PRD Generation](https://github.com/rjmurillo/ai-agents) · [View Workflow](https://github.com/rjmurillo/ai-agents/actions/runs/20392541161)</sub>



### Comment by @github-actions on 12/20/2025 09:43:24

<!-- AI-ISSUE-TRIAGE -->

## AI Triage Summary

> [!NOTE]
> This issue has been automatically triaged by AI agents

<details>
<summary>What is AI Triage?</summary>

This issue was analyzed by AI agents:

- **Analyst Agent**: Categorizes the issue and suggests appropriate labels
- **Roadmap Agent**: Aligns the issue with project milestones and priorities
- **Explainer Agent** (if escalated): Generates comprehensive PRD

</details>

### Triage Results

| Property | Value |
|:---------|:------|
| **Category** | `enhancement` |
| **Labels** | enhancement area-workflows area-infrastructure |
|  **Priority** | `P2` |
| **Milestone** | v1.2 |
| **PRD Escalation** | Generated (see below) |

<details>
<summary>Categorization Analysis</summary>

```json
```json
{
  "labels": ["enhancement", "area-workflows", "area-infrastructure"],
  "category": "enhancement",
  "confidence": 0.92,
  "reasoning": "Issue proposes new DORA metrics feature with PowerShell module, GitHub Actions workflow, and metrics storage infrastructure for tracking AI-assisted development velocity"
}
```

```

</details>

<details>
<summary>Roadmap Alignment</summary>

```json
```json
{
  "milestone": "v1.2",
  "priority": "P2",
  "epic_alignment": "",
  "confidence": 0.80,
  "reasoning": "New feature for metrics dashboard aligns with backlog item 'Performance Metrics Dashboard' at P2; requires research, multi-phase work, and external API integration",
  "escalate_to_prd": true,
  "escalation_criteria": ["feature_request", "research_required", "multi_phase_work", "external_dependency"],
  "complexity_score": 10
}
```

```

</details>

---

<sub>Powered by [AI Issue Triage](https://github.com/rjmurillo/ai-agents) - [View Workflow](https://github.com/rjmurillo/ai-agents/actions/runs/20392541161)</sub>


