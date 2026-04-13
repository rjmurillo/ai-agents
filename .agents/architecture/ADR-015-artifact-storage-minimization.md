# ADR-015: Artifact Storage Minimization Strategy

## Status

Accepted

## Date

2025-12-22

## Context

GitHub Actions artifact storage contributes to metered usage costs. Current state analysis revealed:

1. **Long retention periods**: Some artifacts retained for 90 days (agent-metrics) and 30 days (pester-tests)
2. **Frequent artifact generation**: Weekly and per-PR artifact uploads
3. **Minimal retrieval needs**: Most artifacts are for debugging and rarely accessed after 7 days

GitHub charges for artifact storage on a per-GB-day basis. Reducing retention periods directly reduces costs without impacting workflow functionality.

### Current Artifact Usage

| Workflow | Artifact | Retention | Frequency | Justification |
|----------|----------|-----------|-----------|---------------|
| agent-metrics.yml | metrics report | 90 days | Weekly | Historical analysis |
| pester-tests.yml | test results | 30 days | Per-PR | Compliance records |
| ai-pr-quality-gate.yml | review results | 1 day | Per-PR | Temporary handoff |
| ai-session-protocol.yml | validation results | 1 day | Per-PR | Temporary handoff |

## Decision

**Reduce artifact retention to minimum necessary duration:**

1. **Operational artifacts** (temporary): 1 day (no change)
2. **Test results**: 7 days (reduced from 30 days)
3. **Metrics reports**: 7 days (reduced from 90 days)

## Rationale

### Retention Period Analysis

| Artifact Type | Current | Proposed | Justification |
|---------------|---------|----------|---------------|
| PR review results | 1 day | 1 day | Only needed for aggregation within same workflow run |
| Test results | 30 days | 7 days | Sufficient for debugging recent failures; older results in git history |
| Metrics reports | 90 days | 7 days | Historical data captured in git commits; 7 days allows review of latest report |

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Keep long retention | Historical access | High storage costs | Cost constraint makes this unviable |
| 3-day retention | Moderate savings | May be too short for weekend debugging | 7 days covers full work week + weekend |
| Disable artifacts | Maximum savings | Lose debugging capability | Too aggressive; artifacts provide value |
| Compress artifacts | Reduced storage | Decompression overhead | Minimal benefit for text files |

### Cost Impact

**Storage savings calculation**:
- Pester tests: 30 days → 7 days = 76.7% reduction
- Agent metrics: 90 days → 7 days = 92.2% reduction

**Estimated annual savings**: $100-200 (based on artifact volume)

### Trade-offs

**Chosen**: 7-day retention
- **Pro**: Covers debugging window, significant cost reduction
- **Con**: Cannot access older artifacts
- **Mitigation**: Git history preserves test results and metrics in repository

## Consequences

### Positive

- **76-92% storage cost reduction** for affected artifacts
- **Simplified retention policy**: Single 7-day standard (except operational artifacts at 1 day)
- **Encourages git-based persistence**: Metrics and results tracked in commits
- **Faster artifact cleanup**: Less clutter in GitHub UI

### Negative

- **Older artifacts inaccessible**: Cannot debug issues from >7 days ago using artifacts
- **Potential compliance concern**: Some orgs require longer test result retention
- **Re-run required for historical data**: Must re-run workflows if older artifacts needed

### Neutral

- **No workflow logic changes**: Only retention-days parameter updated
- **No impact on workflow execution**: Artifacts still uploaded and available during retention window

## Implementation Notes

### Changed Retention Periods

1. **agent-metrics.yml**: 90 days → 7 days
   ```yaml
   retention-days: 7  # was: 90
   ```

2. **pester-tests.yml**: 30 days → 7 days
   ```yaml
   retention-days: 7  # was: 30
   ```

### Unchanged Artifacts (Already Minimal)

- **ai-pr-quality-gate.yml**: 1 day (temporary, no change)
- **ai-session-protocol.yml**: 1 day (temporary, no change)

### Monitoring

Track artifact storage costs in GitHub billing dashboard to validate savings.

### Compliance Considerations

For organizations requiring longer retention:
1. Configure repository-level retention settings (overrides workflow settings)
2. Archive critical artifacts to external storage (S3, Azure Blob)
3. Document retention policy exception in compliance records

## Related Decisions

- ADR-025: GitHub Actions ARM Runner Migration
- ADR-016: Workflow Path Filtering Strategy

## References

- [GitHub Actions: Managing artifacts](https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts)
- [GitHub Pricing: Artifact storage costs](https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions)
- [GitHub Actions: Artifact retention policies](https://docs.github.com/en/actions/learn-github-actions/usage-limits-billing-and-administration#artifact-and-log-retention-policy)
- Issue: #[issue-number] - GitHub Actions cost audit and optimization

---

*Template Version: 1.0*
*Created: 2025-12-22*
*GitHub Issue: Cost optimization initiative*
