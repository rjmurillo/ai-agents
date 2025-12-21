# GitHub Actions Cost Governance

> **Status**: Active
> **Created**: 2025-12-20
> **Purpose**: Establish cost-conscious practices for GitHub Actions usage
> **RFC 2119**: This document uses RFC 2119 key words (MUST, SHOULD, MAY)

## Enforcement Summary

**Cost governance is CRITICAL, not optional.** All CI/CD changes MUST comply with:

| Requirement | Level | Reference |
|-------------|-------|-----------|
| ARM runners for new workflows | **MUST** | [ADR-007](./architecture/ADR-007-github-actions-runner-selection.md) |
| Justify non-ARM runner usage | **MUST** | ADR-007 comment in workflow |
| No artifacts unless justified | **MUST** | [ADR-008](./architecture/ADR-008-artifact-storage-minimization.md) |
| Retention ≤7 days for most artifacts | **MUST** | ADR-008 |
| Path filters on workflows | **MUST** | Template below |
| Concurrency to cancel duplicates | **SHOULD** | Template below |

**Violations**: PR reviewers MUST block merges that violate ADR-007 or ADR-008 without documented exceptions.

---

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
| **Use DRAFT PRs until ready** | **80% fewer bot runs** | **P0** | - |
| **Batch commits, push once** | **5x fewer CI triggers** | **P0** | - |
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

## PR Workflow (MUST)

Each push to a non-draft PR triggers multiple bots (Copilot, CodeRabbit, Gemini, CI/CD).

**Requirements:**

| Requirement | Level | Rationale |
|-------------|-------|-----------|
| Create PRs as DRAFT | **MUST** | Avoids bot triggers until ready |
| Batch commits locally | **MUST** | Single push = single bot trigger |
| Push only when ready | **MUST** | 5 pushes = 5x cost |
| Convert to ready-for-review at end | **MUST** | Single review cycle |

**Correct Pattern (Zero-CI approach):**

```bash
# 1) Create feature branch locally
git switch -c feature/my-feature

# 2) Push empty branch to remote (enables draft PR creation)
git push --set-upstream origin feature/my-feature

# 3) Create DRAFT PR immediately (before any work pushes)
gh pr create --draft --title "feat: my feature"

# 4) Work locally, batch commits
git commit -m "feat: part 1"
git commit -m "feat: part 2"
git commit -m "test: add tests"

# 5) Push when ready (already draft - no CI waste)
git push

# 6) Only mark ready when seeking review
gh pr ready
```

**Alternative Pattern (Minimal-CI approach):**

```bash
# 1) Create branch and work locally
git switch -c feature/my-feature
git commit -m "feat: part 1"
git commit -m "feat: part 2"

# 2) Push and immediately create draft (minimize CI window)
git push --set-upstream origin feature/my-feature
gh pr create --draft --title "feat: my feature"  # Create within seconds

# 3) Continue work and push (now draft)
git commit -m "test: add tests"
git push

# 4) Mark ready when seeking review
gh pr ready
```

**Anti-Pattern (AVOID):**

```bash
# DON'T: Commit → Push → Commit → Push (triggers bots each time)
git commit -m "wip" && git push  # Bot run #1
git commit -m "fix" && git push  # Bot run #2
git commit -m "done" && git push # Bot run #3
# Result: 3x the cost
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

---

## Claude API Token Efficiency

Token costs are the other major cost driver. Apply these practices:

| Requirement | Level | Impact |
|-------------|-------|--------|
| Use Serena symbolic tools over file reads | **MUST** | 80%+ token reduction |
| Read memories before work (enables caching) | **MUST** | Cache: $1.50/M vs $15/M |
| Use Haiku for quick tasks | **SHOULD** | Haiku: $0.25/M vs Opus: $15/M |
| Limit file reads with offset/limit | **SHOULD** | Reduces context bloat |

### Token Cost Reference

| Model | Input (no cache) | Input (cache read) | Output |
|-------|-----------------|-------------------|--------|
| Claude Opus 4.5 | $15/M | $1.50/M | $75/M |
| Claude Sonnet 4.5 | $3/M | $0.30/M | $15/M |
| Claude Haiku 4.5 | $0.25/M | $0.025/M | $1.25/M |

**Key Insight**: A 100M token uncached Opus session costs $1,500. The same work with caching: ~$150. With Haiku where appropriate: ~$25.

---

## Related Documents

- [ADR-007: GitHub Actions Runner Selection](./architecture/ADR-007-github-actions-runner-selection.md) - ARM-first runner policy
- [ADR-008: Artifact Storage Minimization](./architecture/ADR-008-artifact-storage-minimization.md) - No artifacts by default
- [SERENA-BEST-PRACTICES.md](./SERENA-BEST-PRACTICES.md) - Token-efficient Serena usage

## References

- [GitHub Actions Billing](https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions)
- [Actions Runner Pricing](https://docs.github.com/en/billing/reference/actions-runner-pricing)
- [GitHub-Hosted Runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Spending Limits](https://docs.github.com/en/billing/managing-billing-for-github-actions/managing-your-spending-limit-for-github-actions)
- [GitHub Pricing Calculator](https://github.com/pricing/calculator)
