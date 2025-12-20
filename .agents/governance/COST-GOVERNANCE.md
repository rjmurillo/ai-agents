# GitHub Actions Cost Governance

> **Status**: Active
> **Created**: 2025-12-20
> **Purpose**: Establish cost-conscious practices for GitHub Actions usage

## GitHub Actions Pricing Reference

### Runner Per-Minute Rates (as of December 2025)

| Runner Type | Per-Minute Rate | Relative Cost | Notes |
|-------------|-----------------|---------------|-------|
| Linux 2-core (`ubuntu-latest`) | $0.008 | 1x (baseline) | Standard for most workflows |
| Linux 2-core ARM (`ubuntu-24.04-arm`) | $0.005 | 0.625x | **37.5% cheaper** - preferred |
| Windows 2-core (`windows-latest`) | $0.016 | 2x | Use only when required |
| macOS 3-core (`macos-latest`) | $0.080 | 10x | Avoid unless necessary |

### Price Changes (January 1, 2026)

GitHub is reducing rates for many runners:

- Linux 2-core: $0.008 → $0.006 (-25%)
- Windows 2-core: $0.016 → $0.010 (-38%)

### Storage Costs

| Resource | Rate | Notes |
|----------|------|-------|
| Artifact storage | $0.25/GB/month | Billed daily at ~$0.008/GB/day |
| Actions cache | Included | Up to 10GB per repository |

### Free Tier (Public Repositories)

- Standard GitHub-hosted runners: **Free and unlimited**
- Larger runners: Not available on free tier

### Free Tier (Private Repositories)

| Plan | Included Minutes/Month | Storage |
|------|------------------------|---------|
| Free | 2,000 | 500 MB |
| Pro | 3,000 | 1 GB |
| Team | 3,000 | 2 GB |
| Enterprise | 50,000 | 50 GB |

**Note**: Minutes are consumed at different rates by runner type (Windows = 2x, macOS = 10x).

## Cost Optimization Strategies

### Primary Cost Drivers

1. **Frequent Workflow Runs**: Every PR and push triggers multiple workflows
2. **Long-Running Jobs**: Some jobs run for extended periods
3. **Windows Runners**: 2x cost of Linux runners
4. **Artifact Accumulation**: Large retention periods

### Optimization Actions

| Action | Expected Savings | Priority | ADR |
|--------|------------------|----------|-----|
| Migrate to ARM runners | 35-40% on runner costs | P0 | ADR-007 |
| Reduce artifact retention | 60-80% on storage | P0 | ADR-008 |
| Add path filters to workflows | 40-60% fewer runs | P0 | - |
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

## Monitoring

### Check Current Usage

```bash
# Check billing for organization (requires admin)
gh api /orgs/{org}/settings/billing/actions

# Check billing for user account
gh api /user/settings/billing/actions
```

### Cost Alerts

Configure spending alerts in GitHub Settings → Billing → Actions:

- Set warning thresholds based on your budget
- Review usage weekly during active development
- Monthly review during maintenance periods

## Related ADRs

- [ADR-007: GitHub Actions Runner Selection](./architecture/ADR-007-github-actions-runner-selection.md)
- [ADR-008: Artifact Storage Minimization](./architecture/ADR-008-artifact-storage-minimization.md)

## References

- [GitHub Actions Billing](https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions)
- [Actions Runner Pricing](https://docs.github.com/en/billing/reference/actions-runner-pricing)
- [GitHub-Hosted Runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Spending Limits](https://docs.github.com/en/billing/managing-billing-for-github-actions/managing-your-spending-limit-for-github-actions)
- [GitHub Pricing Calculator](https://github.com/pricing/calculator)
