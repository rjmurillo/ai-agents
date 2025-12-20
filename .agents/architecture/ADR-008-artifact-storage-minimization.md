# ADR-008: Artifact Storage Minimization

## Status

Accepted

## Date

2025-12-20

## Context

GitHub Actions charges for artifact storage at $0.000336 per GB per day (approximately $0.01/GB/month). While individual artifacts may seem cheap, accumulated storage from frequent CI runs can add up:

| Scenario | Daily Runs | Artifact Size | Monthly Cost |
|----------|------------|---------------|--------------|
| Small project | 10 | 50 MB | ~$0.50 |
| Medium project | 50 | 100 MB | ~$5.00 |
| Active project | 100 | 200 MB | ~$20.00 |

Additionally, artifact upload/download times affect workflow duration, indirectly increasing runner costs.

### Forces

1. **Cost**: Storage fees accumulate, especially with long retention
2. **Performance**: Large artifacts slow down workflow execution
3. **Debugging Value**: Artifacts provide post-run debugging capability
4. **Compliance**: Some artifacts may be required for audit trails
5. **Disk Space**: GitHub has account-level storage limits

## Decision

We will minimize artifact storage through the following policies:

### 1. Default: No Artifacts

New workflows MUST NOT upload artifacts unless explicitly justified.

### 2. Justified Artifact Types

| Artifact Type | Justification Required | Retention | Max Size |
|---------------|----------------------|-----------|----------|
| Test results (XML/JSON) | Recommended for CI visibility | 7 days | 10 MB |
| Build outputs | Only if consumed by dependent workflow | 1 day | 50 MB |
| Coverage reports | If coverage tracking enabled | 7 days | 5 MB |
| Debug logs | Only on failure | 3 days | 20 MB |
| Binaries/packages | Only for release workflows | 30 days | 100 MB |

### 3. Artifact Hygiene Rules

1. **Compression**: Always use compression for text-based artifacts
2. **Selective Upload**: Upload only necessary files, not entire directories
3. **Conditional Upload**: Use `if: failure()` for debug artifacts
4. **Short Retention**: Default to minimum retention period needed
5. **Cleanup**: Implement artifact deletion for superseded runs

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Upload everything | Maximum debugging capability | High cost, slow workflows | Not economical |
| Never upload | Zero storage cost | Loss of debugging, no CI visibility | Too restrictive |
| Long retention (90 days) | Extended debugging window | 12x storage cost | Rarely needed |
| External storage (S3) | More control | Additional complexity, separate costs | Over-engineered |

### Trade-offs

- **Debugging vs Cost**: Limiting artifacts may make debugging harder, but 7-day retention covers most cases
- **Automation vs Manual**: Requires discipline in workflow authoring
- **Visibility vs Efficiency**: Test result artifacts are worth the cost for CI visibility

## Consequences

### Positive

- Reduced storage costs by 60-80%
- Faster workflow execution (less upload/download time)
- Cleaner artifact management
- Forces intentional decisions about what to preserve

### Negative

- May need to re-run workflows to capture missing artifacts
- Requires documentation of artifact decisions
- Short retention may miss delayed debugging needs

### Neutral

- Existing workflows need audit and update
- No impact on workflow logic beyond artifact steps

## Implementation Notes

### Recommended Test Results Upload

```yaml
- name: Upload Test Results
  # ADR-008: Test results justified for CI visibility
  uses: actions/upload-artifact@v4
  if: always()
  with:
    name: test-results
    path: TestResults/*.xml
    retention-days: 7
    compression-level: 9
```

### Conditional Debug Upload

```yaml
- name: Upload Debug Logs
  # ADR-008: Debug logs only on failure
  uses: actions/upload-artifact@v4
  if: failure()
  with:
    name: debug-logs-${{ github.run_id }}
    path: |
      logs/*.log
      !logs/verbose-*.log
    retention-days: 3
```

### Artifact Justification Comment

Every `upload-artifact` step MUST include a comment explaining:

1. Why this artifact is needed
2. Why the retention period was chosen
3. Reference to this ADR

Example:

```yaml
# ADR-008: Coverage report enables trend tracking in Codecov
# 7-day retention aligns with PR merge cycle
```

### Migration Checklist

- [ ] Audit existing workflows for artifact uploads
- [ ] Remove unjustified artifact uploads
- [ ] Reduce retention periods to minimums
- [ ] Add compression to text artifacts
- [ ] Add ADR-008 comments to justified artifacts
- [ ] Implement `if: failure()` for debug artifacts

## Related Decisions

- ADR-007: GitHub Actions Runner Selection (cost-related)
- ADR-006: Thin Workflows, Testable Modules (workflow architecture)

## References

- [GitHub Actions Storage Billing](https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions#about-billing-for-github-actions)
- [Artifact Retention Policies](https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts#configuring-a-custom-artifact-retention-period)
- Session 38: Cost optimization discussion

---

*Template Version: 1.0*
*Created: 2025-12-20*
