# Workflow Run Coalescing Metrics

## Report Period

- **From**: (Baseline report to be generated)
- **To**: (Baseline report to be generated)
- **Generated**: (Baseline report to be generated)

## Executive Summary

This metrics report tracks the effectiveness of GitHub Actions workflow run coalescing for AI-powered workflows in the repository. Coalescing occurs when rapid successive commits to the same PR trigger concurrent workflow runs, and the concurrency control mechanism cancels in-progress runs to start fresh with the latest commit.

**Key Metrics**:

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Coalescing Effectiveness | TBD | 90% | TBD |
| Race Condition Rate | TBD | <10% | TBD |
| Average Cancellation Time | TBD | <5s | TBD |

## Purpose

This report provides visibility into:

1. **Coalescing Effectiveness**: Percentage of overlapping runs successfully cancelled vs. running in parallel (race condition)
2. **Race Condition Rate**: How often the concurrency control fails to prevent parallel runs
3. **Cancellation Performance**: Time taken to detect and cancel superseded runs

## Workflow Run Analysis

### Total Runs Summary

- **Total Workflow Runs**: TBD
- **Cancelled Runs**: TBD
- **Successful Coalescing Events**: TBD
- **Race Conditions Detected**: TBD

### Monitored Workflows

The following AI-powered workflows are monitored for coalescing behavior:

- `ai-pr-quality-gate`
- `ai-spec-validation`
- `ai-session-protocol`
- `pr-validation`
- `label-pr`
- `memory-validation`
- `auto-assign-reviewer`

## Data Collection

This report is generated automatically using:

- **Script**: `.github/scripts/Measure-WorkflowCoalescing.ps1`
- **Workflow**: `.github/workflows/workflow-coalescing-metrics.yml`
- **Schedule**: Weekly on Monday 9 AM UTC
- **Data Source**: GitHub Actions API (`/repos/{owner}/{repo}/actions/runs`)

## How to Generate Manually

```bash
# Analyze last 30 days
pwsh .github/scripts/Measure-WorkflowCoalescing.ps1

# Analyze last 90 days with JSON output
pwsh .github/scripts/Measure-WorkflowCoalescing.ps1 -Since 90 -Output Json

# Analyze specific workflows
pwsh .github/scripts/Measure-WorkflowCoalescing.ps1 -Workflows @('ai-pr-quality-gate', 'ai-spec-validation')
```

## Understanding the Metrics

### Coalescing Effectiveness

**Formula**: `(Cancelled Runs / (Cancelled Runs + Parallel Runs)) * 100`

**What it measures**: How well the concurrency control prevents redundant work by cancelling superseded runs.

**Target**: 90%+ (per ADR-026 observed baseline)

### Race Condition Rate

**Formula**: `(Parallel Runs / Total Runs) * 100`

**What it measures**: How often two or more runs execute concurrently despite concurrency control.

**Target**: <10%

**Causes**:
- Extremely rapid commits (faster than GitHub Actions can detect and cancel)
- GitHub Actions infrastructure delay
- Workflow startup time before cancellation can occur

### Average Cancellation Time

**What it measures**: Time from run creation to cancellation for successfully coalesced runs.

**Target**: <5 seconds

**Impact**: Shorter cancellation time reduces wasted compute resources.

## Related Documentation

- [ADR-026: PR Automation Concurrency and Safety](.agents/architecture/ADR-026-pr-automation-concurrency-and-safety.md)
- [Agent Metrics](docs/agent-metrics.md)
- [Workflow Patterns](.agents/governance/workflow-patterns.md)

---

*This baseline report will be replaced with actual metrics data after the first automated collection.*
