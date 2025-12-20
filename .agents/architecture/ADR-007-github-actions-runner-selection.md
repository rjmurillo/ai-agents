# ADR-007: GitHub Actions Runner Selection

## Status

Accepted

## Date

2025-12-20

## RFC 2119 Compliance

This ADR uses RFC 2119 key words:

- **MUST** / **REQUIRED** / **SHALL**: Absolute requirement; violation requires documented exception
- **MUST NOT** / **SHALL NOT**: Absolute prohibition
- **SHOULD** / **RECOMMENDED**: Strong recommendation; deviation requires justification
- **MAY** / **OPTIONAL**: Truly optional

## Context

GitHub Actions charges per-minute for workflow execution, with costs varying significantly by runner type:

| Runner | Cost/Minute | Cost/Hour | Relative Cost |
|--------|-------------|-----------|---------------|
| `ubuntu-latest` | $0.000133 | $0.008 | 1x (baseline) |
| `ubuntu-24.04-arm` | $0.000083 | $0.005 | 0.625x |
| `windows-latest` | $0.000267 | $0.016 | 2x |

Our workflows run frequently (on every PR and push to main), accumulating significant costs over time. We need a consistent policy for runner selection that balances cost, performance, and compatibility.

### Forces

1. **Cost Efficiency**: ARM runners are 37.5% cheaper than x64 Linux runners
2. **Compatibility**: Some tools may not have ARM builds or have different behavior
3. **Performance**: ARM runners may have different performance characteristics
4. **Ecosystem Support**: PowerShell Core runs on all three platforms
5. **Maintainability**: Consistent runner selection reduces cognitive overhead

## Decision

All workflows MUST follow this runner selection hierarchy:

1. **Default (MUST)**: New workflows MUST use `ubuntu-24.04-arm`
2. **Fallback (SHOULD NOT)**: `ubuntu-latest` SHOULD NOT be used unless ARM compatibility issues are documented
3. **Windows (MUST justify)**: `windows-latest` MUST NOT be used unless Windows-specific testing is required AND documented

### Enforcement Requirements

| Requirement | Level | Verification |
|-------------|-------|--------------|
| New workflows use ARM runner | **MUST** | PR review checklist |
| Non-ARM runner has justification comment | **MUST** | Comment in workflow file |
| Windows runner has Windows-only justification | **MUST** | ADR-007 exception documented |
| macOS runner avoided unless required | **SHOULD** | Cost impact documented |

### Selection Criteria

| Criterion | Use ARM (`ubuntu-24.04-arm`) | Use x64 (`ubuntu-latest`) | Use Windows |
|-----------|------------------------------|---------------------------|-------------|
| PowerShell scripts | ✅ | If ARM issues | For Windows-only features |
| Node.js/npm | ✅ | If ARM issues | ❌ |
| Python tools | ✅ | If ARM issues | ❌ |
| Docker builds | Check base image | ✅ multi-arch | ❌ |
| .NET builds | ✅ | If ARM issues | For Windows-specific |
| Shell scripts | ✅ | ❌ | ❌ |
| Windows-only tools | ❌ | ❌ | ✅ |

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Always use `ubuntu-latest` | Maximum compatibility, familiar | 60% more expensive than ARM | Cost inefficient |
| Always use Windows | PowerShell native support | 2x cost of Linux, slower startup | Far too expensive |
| Mixed without policy | Flexibility | Inconsistent, hard to maintain | No governance |
| Self-hosted runners | Full control, potentially free | Maintenance burden, security risk | Out of scope |

### Trade-offs

- **ARM First**: Saves 37.5% on most workflow runs, but may require occasional fallback for compatibility
- **Explicit Windows**: Only used when genuinely needed, prevents accidental 2x cost increases
- **Documentation Requirement**: Every deviation from ARM must be documented in workflow comments

## Consequences

### Positive

- Reduced CI/CD costs by approximately 35-40%
- Consistent runner selection across workflows
- Clear decision framework for new workflows
- ARM runners often have faster cold-start times

### Negative

- May encounter occasional ARM compatibility issues
- Need to maintain awareness of tool ARM support
- Slight cognitive overhead for migration

### Neutral

- Existing workflows need gradual migration
- No impact on workflow logic, only runner selection

## Implementation Notes

### Workflow Template

```yaml
jobs:
  build:
    # ADR-007: Use ARM runner for cost efficiency (37.5% savings)
    runs-on: ubuntu-24.04-arm

    steps:
      # ... workflow steps
```

### When Fallback is Needed

```yaml
jobs:
  build:
    # ADR-007: Using x64 due to [specific tool] ARM incompatibility
    # TODO: Re-evaluate when [tool] adds ARM support
    runs-on: ubuntu-latest
```

### Migration Checklist

- [ ] Audit existing workflows for runner usage
- [ ] Create tracking issue for ARM migration
- [ ] Test each workflow on ARM runner
- [ ] Document any compatibility issues
- [ ] Update workflows with ADR-007 comments

## Related Decisions

- ADR-008: Artifact Storage Minimization (cost-related)
- ADR-006: Thin Workflows, Testable Modules (workflow architecture)

## References

- [GitHub Actions Pricing](https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions)
- [ARM Runner Announcement](https://github.blog/changelog/2024-06-03-github-actions-arm-based-linux-and-windows-runners-are-now-in-public-beta/)
- Session 38: Cost optimization discussion

---

*Template Version: 1.0*
*Created: 2025-12-20*
