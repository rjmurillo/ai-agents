# GitHub Actions Cost Governance

## Overview

This document establishes cost governance policies for GitHub Actions usage to ensure sustainable CI/CD operations within budget constraints.

**Target**: Monthly GitHub Actions costs under $100 USD
**Current baseline** (December 2025): $243.55

## Cost Optimization Strategy

### 1. Runner Selection (ADR-014)

**Policy**: Use ARM runners for all Linux workloads.

| Runner Type | Use Case | Cost Impact |
|-------------|----------|-------------|
| ubuntu-24.04-arm | Default for Linux jobs | 37.5% savings vs x64 |
| ubuntu-latest (x64) | Exception only (document justification) | Baseline cost |
| windows-latest | Windows-specific workloads only | Higher cost, unavoidable |

**Savings**: ~37.5% reduction on Linux workflows = $1,800/year

### 2. Artifact Storage (ADR-015)

**Policy**: Minimize retention periods to operational needs.

| Artifact Type | Retention Period | Justification |
|---------------|------------------|---------------|
| Temporary operational | 1 day | Handoff between jobs in same workflow |
| Test results | 7 days | Debugging window for recent failures |
| Metrics reports | 7 days | Review window; historical data in git |
| Long-term compliance | 30+ days | Exception only (document regulatory requirement) |

**Savings**: ~80% reduction in artifact storage costs = $150/year

### 3. Workflow Execution (ADR-016)

**Policy**: Prevent unnecessary and duplicate workflow runs.

#### Path Filters

All workflows must use path filters to restrict execution to relevant file changes:

```yaml
on:
  push:
    paths:
      - 'relevant-path/**'
      - '.github/workflows/this-workflow.yml'
```

**Exceptions**:

- Issue-triggered workflows (no files changed)
- PR workflows with internal path filtering (dorny/paths-filter)
- Workflows that analyze entire repository

#### Concurrency Groups

All workflows must implement concurrency control:

```yaml
concurrency:
  group: workflow-name-${{ github.ref || github.event.issue.number }}
  cancel-in-progress: true  # false for issue-based workflows
```

**cancel-in-progress: true** for:

- Branch/PR workflows (rapid commits should cancel outdated runs)
- Scheduled workflows (new trigger should cancel old run)

**cancel-in-progress: false** for:

- Issue-based workflows (avoid race conditions)
- Critical deployment workflows (preserve all runs)

**Savings**: ~30% reduction in workflow minutes = $400/year

## Cost Monitoring

### Monthly Review Checklist

1. **Review billing dashboard**: Check current month's metered usage
2. **Analyze top consumers**: Identify workflows with highest costs
3. **Validate optimizations**: Ensure path filters and concurrency groups are effective
4. **Investigate anomalies**: Flag unexpected cost spikes
5. **Update projections**: Forecast end-of-month costs

### Cost Alerts

Set up GitHub billing alerts at:

- **$50**: Warning threshold (50% of budget)
- **$80**: Action required (80% of budget)
- **$100**: Budget exceeded (emergency review)

### Metrics to Track

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Monthly workflow minutes | <10,000 | TBD | Monitor |
| Monthly artifact storage (GB-days) | <50 | TBD | Monitor |
| Cost per workflow run | <$0.01 | TBD | Monitor |
| False negative rate (path filters) | <1% | TBD | Monitor |

## Workflow Cost Analysis

### High-Cost Workflows

| Workflow | Est. Monthly Cost | Optimization Status |
|----------|------------------|---------------------|
| ai-pr-quality-gate | $30-40 | ✅ ARM, concurrency, internal path filter |
| pester-tests | $20-30 | ✅ ARM (check-paths only), concurrency, path filter |
| ai-issue-triage | $15-20 | ✅ ARM, concurrency |
| ai-session-protocol | $10-15 | ✅ ARM, concurrency, path filter |

### Medium-Cost Workflows

| Workflow | Est. Monthly Cost | Optimization Status |
|----------|------------------|---------------------|
| ai-spec-validation | $8-12 | ✅ ARM, concurrency, path filter |
| copilot-context-synthesis | $8-12 | ✅ ARM, concurrency |
| validate-generated-agents | $5-10 | ⚠️ Windows (no ARM), concurrency, path filter |
| drift-detection | $3-5 | ✅ ARM, concurrency, path filter |

### Low-Cost Workflows

| Workflow | Est. Monthly Cost | Optimization Status |
|----------|------------------|---------------------|
| agent-metrics | $2-3 | ✅ ARM, concurrency, path filter |
| copilot-setup-steps | $1-2 | ✅ ARM, concurrency, path filter |
| label-issues | $1-2 | ✅ ARM, concurrency |
| label-pr | $1-2 | ✅ ARM, concurrency |
| validate-paths | $1-2 | ✅ ARM, concurrency |
| validate-planning-artifacts | $1-2 | ✅ ARM, concurrency, path filter |

## Exception Process

### Requesting Exceptions

To request an exception to cost governance policies:

1. **Document justification**: Explain why exception is needed
2. **Quantify cost impact**: Estimate additional monthly cost
3. **Propose mitigation**: How to minimize cost increase
4. **Submit PR**: Update this document with exception details

### Approved Exceptions

| Exception | Justification | Cost Impact | Mitigation |
|-----------|---------------|-------------|------------|
| validate-generated-agents (Windows) | PowerShell generation requires Windows | +$5/mo | Path filter, concurrency control |
| pester-tests test job (Windows) | Pester tests require PowerShell on Windows | +$20/mo | Path filter, concurrency control |

## Emergency Cost Control

If monthly costs exceed $100:

1. **Immediate**: Disable non-critical scheduled workflows
2. **Short-term**: Increase path filter restrictiveness
3. **Medium-term**: Reduce scheduled workflow frequency
4. **Long-term**: Re-architect workflows for efficiency

### Non-Critical Workflows (Safe to Disable Temporarily)

- agent-metrics (weekly)
- drift-detection (weekly)
- copilot-context-synthesis (hourly sweep)
- ai-issue-triage (hourly sweep)

### Critical Workflows (Never Disable)

- ai-pr-quality-gate (blocks merge)
- pester-tests (blocks merge)
- validate-generated-agents (blocks merge)
- ai-session-protocol (blocks merge)
- ai-spec-validation (blocks merge)

## Best Practices

### Workflow Design

1. **Use dorny/paths-filter** for complex path logic instead of top-level path filters
2. **Implement early exit** for skip conditions to minimize billable minutes
3. **Cache dependencies** (npm, pip, etc.) to reduce installation time
4. **Run fast checks first** (linting, formatting) before expensive tests
5. **Use matrix builds judiciously** (each matrix leg multiplies cost)

### Runner Usage

1. **Prefer ARM runners** unless x64-specific dependencies
2. **Use ubuntu-24.04-arm** (not ubuntu-latest) for explicit ARM
3. **Avoid ubuntu-latest** (x64) unless documented exception
4. **Use smallest runner** for the job (standard, not large)

### Artifact Management

1. **Delete artifacts programmatically** when no longer needed
2. **Use job outputs** for small data instead of artifacts
3. **Compress large artifacts** before upload
4. **Avoid uploading build artifacts** (use caching instead)

## Review Schedule

- **Weekly**: Review high-cost workflows for anomalies
- **Monthly**: Full cost review and optimization opportunities
- **Quarterly**: Revisit cost governance policies and targets

## References

- ADR-014: GitHub Actions ARM Runner Migration
- ADR-015: Artifact Storage Minimization Strategy
- ADR-016: Workflow Execution Optimization Strategy
- [GitHub Pricing: Actions](https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions)
- [GitHub Actions: Usage limits](https://docs.github.com/en/actions/learn-github-actions/usage-limits-billing-and-administration)

---

**Last Updated**: 2025-12-22
**Next Review**: 2026-01-22
**Owner**: DevOps Team
