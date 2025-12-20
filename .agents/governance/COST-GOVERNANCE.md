# GitHub Actions Cost Governance

> **Status**: Active
> **Created**: 2025-12-20
> **Trigger**: Monthly metered usage exceeded $243 with projection of $500+

## Current Costs (December 2025)

| Category | Current | Projected | Target |
|----------|---------|-----------|--------|
| **Total Metered** | $243.55 | $500+ | <$100 |
| Runner minutes | ~$200+ | ~$400+ | <$80 |
| Artifact storage | ~$40+ | ~$80+ | <$20 |

## Cost Drivers Analysis

### Primary Cost Drivers

1. **Frequent Workflow Runs**: Every PR and push triggers multiple workflows
2. **Long-Running Jobs**: Some jobs run for extended periods
3. **Windows Runners**: 2x cost of Linux runners
4. **Artifact Accumulation**: Large retention periods

### Immediate Actions Required

| Action | Expected Savings | Priority | ADR |
|--------|------------------|----------|-----|
| Migrate to ARM runners | 35-40% on runner costs | P0 | ADR-007 |
| Reduce artifact retention | 60-80% on storage | P0 | ADR-008 |
| Add path filters to workflows | 40-60% fewer runs | P0 | New |
| Consolidate redundant workflows | 20-30% fewer runs | P1 | - |
| Cancel duplicate runs | 10-20% reduction | P1 | - |

## Workflow Audit Checklist

For each workflow, verify:

- [ ] Uses `ubuntu-24.04-arm` unless documented exception
- [ ] Has path filters to prevent unnecessary runs
- [ ] Artifacts have minimal retention (1-7 days)
- [ ] Uses `concurrency` to cancel duplicate runs
- [ ] No Windows runner unless absolutely required
- [ ] Debug artifacts conditional on failure only

## Path Filter Template

Add to every workflow to prevent unnecessary runs:

```yaml
on:
  push:
    branches: [main]
    paths:
      - 'src/**'           # Only trigger on relevant paths
      - '.github/workflows/this-workflow.yml'
  pull_request:
    branches: [main]
    paths:
      - 'src/**'
      - '.github/workflows/this-workflow.yml'
```

## Concurrency Template

Prevent duplicate runs on same branch:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

## Monthly Cost Targets

| Month | Target | Strategy |
|-------|--------|----------|
| Dec 2025 | <$500 (limit damage) | Immediate ARM migration, path filters |
| Jan 2026 | <$200 | Full workflow audit, artifact cleanup |
| Feb 2026 | <$100 | Optimized steady state |
| Ongoing | <$100 | Monthly review, continuous optimization |

## Monitoring

### Weekly Cost Check

```bash
# Check current billing (requires admin access)
gh api /orgs/{org}/settings/billing/actions
```

### Cost Alerts

Set up spending alerts at:
- $100 (warning)
- $200 (action required)
- $300 (escalation)

## Related ADRs

- [ADR-007: GitHub Actions Runner Selection](./architecture/ADR-007-github-actions-runner-selection.md)
- [ADR-008: Artifact Storage Minimization](./architecture/ADR-008-artifact-storage-minimization.md)

## References

- [GitHub Actions Billing](https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions)
- [Spending Limits](https://docs.github.com/en/billing/managing-billing-for-github-actions/managing-your-spending-limit-for-github-actions)
