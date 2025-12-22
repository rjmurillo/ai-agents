# ADR-014: GitHub Actions ARM Runner Migration

## Status

Accepted

## Date

2025-12-22

## Context

GitHub Actions metered usage reached $243.55 in December 2025 with projected monthly costs exceeding $500 USD. The target cost is less than $100/month. Analysis revealed opportunities for significant cost reduction through:

1. **Runner type optimization**: ubuntu-latest (x64) runners cost 37.5% more than ubuntu-24.04-arm runners
2. **Unnecessary workflow executions**: Workflows running on irrelevant file changes
3. **Duplicate runs**: Multiple concurrent workflow runs for the same PR/branch
4. **Artifact storage costs**: Long retention periods and uncompressed artifacts

The repository has 14 workflows with varying runner requirements:
- 12 workflows using Linux runners (ARM-compatible)
- 2 workflows requiring Windows runners (validate-generated-agents, pester-tests test job)

## Decision

**Migrate all Linux-based workflows from ubuntu-latest to ubuntu-24.04-arm runners.**

Windows-based workflows remain unchanged as ARM runners are not available for Windows.

## Rationale

### Cost Analysis

| Runner Type | Cost per Minute | Annual Cost (100 hrs) | Savings vs x64 |
|-------------|-----------------|----------------------|----------------|
| ubuntu-latest (x64) | Standard rate | $X | Baseline |
| ubuntu-24.04-arm | 37.5% less | $Y | 37.5% |
| windows-latest | Higher rate | $Z | N/A |

**Projected Annual Savings**: 37.5% reduction on Linux workflows = ~$1,800 (assuming $6,000 baseline)

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Keep ubuntu-latest | No migration risk, proven compatibility | 37.5% higher costs, unsustainable at scale | Cost constraint makes this unviable |
| Self-hosted runners | Zero per-minute cost, full control | Infrastructure overhead, security concerns, maintenance burden | Not cost-effective for current scale |
| Reduce workflow frequency | Lower absolute cost | Slower feedback, reduced quality gates | Compromises development velocity |
| ubuntu-22.04-arm | ARM cost savings | Older Ubuntu version, shorter support window | ubuntu-24.04-arm provides better long-term support |

### Trade-offs

**Chosen**: ubuntu-24.04-arm
- **Pro**: 37.5% cost reduction, latest LTS, 10-year support until 2034
- **Con**: Potential ARM-specific compatibility issues, newer platform may have edge cases
- **Mitigation**: Thorough testing, monitoring for ARM-specific issues

## Consequences

### Positive

- **37.5% cost reduction** on Linux-based workflows (estimated $1,800/year savings)
- **Latest Ubuntu LTS**: ubuntu-24.04 has 10-year support (until 2034)
- **Future-proof**: ARM architecture adoption aligns with industry trends
- **Same GitHub-managed infrastructure**: No self-hosting overhead

### Negative

- **Potential compatibility issues**: Some tools may have ARM-specific bugs
- **Slightly newer platform**: ubuntu-24.04-arm may have less community documentation than x64
- **One-time migration effort**: All workflows need testing and validation

### Neutral

- **Windows workflows unchanged**: No impact on Windows-based jobs
- **Existing workflow logic preserved**: Only runner type changes
- **No performance impact expected**: ARM runners have comparable performance

## Implementation Notes

### Migration Checklist

1. **Update runner specifications**:
   ```yaml
   # Before
   runs-on: ubuntu-latest
   
   # After
   runs-on: ubuntu-24.04-arm
   ```

2. **Workflows migrated** (12 total):
   - agent-metrics.yml (2 jobs)
   - ai-issue-triage.yml (2 jobs)
   - ai-pr-quality-gate.yml (4 jobs)
   - ai-session-protocol.yml (3 jobs)
   - ai-spec-validation.yml (1 job)
   - copilot-context-synthesis.yml (2 jobs)
   - copilot-setup-steps.yml (1 job)
   - drift-detection.yml (1 job)
   - label-issues.yml (1 job)
   - label-pr.yml (1 job)
   - pester-tests.yml (2 jobs: check-paths, skip-tests)
   - validate-paths.yml (3 jobs)
   - validate-planning-artifacts.yml (1 job)

3. **Workflows unchanged** (Windows-dependent):
   - validate-generated-agents.yml (windows-latest)
   - pester-tests.yml (test job uses windows-latest for PowerShell)

### Validation Steps

1. Monitor initial workflow runs for ARM-specific failures
2. Verify all actions and tools are ARM-compatible
3. Check for performance regressions
4. Track cost metrics in GitHub billing dashboard

### Rollback Plan

If critical ARM compatibility issues are discovered:
1. Revert to ubuntu-latest in affected workflows
2. Document specific incompatibilities
3. Create targeted exceptions for problematic workflows

## Related Decisions

- ADR-015: Artifact Storage Minimization
- ADR-016: Workflow Path Filtering Strategy
- ADR-006: Thin Workflows, Testable Modules (related to workflow efficiency)

## References

- [GitHub Actions: Ubuntu 24.04 ARM runners announcement](https://github.blog/changelog/2024-06-03-github-actions-ubuntu-24-04-is-now-generally-available/)
- [GitHub Pricing: ARM runner cost savings](https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions)
- [Ubuntu 24.04 LTS release notes](https://ubuntu.com/blog/ubuntu-24-04-lts-noble-numbat-now-available)
- Issue: #[issue-number] - GitHub Actions cost audit and optimization

---

*Template Version: 1.0*
*Created: 2025-12-22*
*GitHub Issue: Cost optimization initiative*
