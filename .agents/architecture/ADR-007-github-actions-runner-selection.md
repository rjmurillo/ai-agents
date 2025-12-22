# ADR-007: GitHub Actions Runner Selection

## Status

**REJECTED**

> **Rejection Reason**: The cost analysis is based on incorrect assumptions. This public repository has **FREE** GitHub Actions usage for standard runners (both x64 and ARM). There is no cost benefit to switching architectures.

## Date

2025-12-20

## Rejection Date

2025-12-21

## RFC 2119 Compliance

This ADR uses RFC 2119 key words:

- **MUST** / **REQUIRED** / **SHALL**: Absolute requirement; violation requires documented exception
- **MUST NOT** / **SHALL NOT**: Absolute prohibition
- **SHOULD** / **RECOMMENDED**: Strong recommendation; deviation requires justification
- **MAY** / **OPTIONAL**: Truly optional

## Context

GitHub Actions charges per-minute for workflow execution, with costs varying significantly by runner type:

| Runner | Cost/Minute (Private Repos) | Public Repos |
|--------|-------------|-----------|
| `ubuntu-latest` | $0.008 | **FREE** |
| `ubuntu-24.04-arm` | $0.005 | **FREE** |
| `windows-latest` | $0.016 | **FREE** |

> **CRITICAL**: As of January 2025, [Linux arm64 hosted runners are FREE for public repositories](https://github.blog/changelog/2025-01-16-linux-arm64-hosted-runners-now-available-for-free-in-public-repositories-public-preview/). The ai-agents repository is **PUBLIC**, so there is **NO cost difference** between runner architectures.

### Original Forces (Corrected)

1. ~~**Cost Efficiency**: ARM runners are 37.5% cheaper than x64 Linux runners~~ → **FALSE for public repos**
2. **Compatibility**: Some tools may not have ARM builds or have different behavior → **TRUE, risk remains**
3. **Performance**: ARM Cobalt 100 processors offer up to 40% better CPU performance → **TRUE, potential benefit**
4. **Ecosystem Support**: PowerShell Core runs on all three platforms → **TRUE**
5. **Maintainability**: Consistent runner selection reduces cognitive overhead → **TRUE**

## Decision

**This ADR is REJECTED.** The cost-based justification is invalid for this public repository.

### Recommended Alternative

For this public repository, runner selection SHOULD be based on:

1. **Compatibility First (MUST)**: Use the runner that has the widest tool support (`ubuntu-latest`)
2. **Performance Second (MAY)**: Switch to ARM only when performance testing confirms benefits AND all tools are ARM-compatible
3. **Windows When Required (MUST justify)**: `windows-latest` only for Windows-specific testing

### Why Not ARM by Default

| Factor | Weight | ARM Impact |
|--------|--------|------------|
| Cost savings | ~~High~~ **Zero** | No benefit for public repos |
| Compatibility risk | Medium | Potential breakage |
| Performance gain | Low-Medium | ~40% faster CPU (unvalidated for our workloads) |
| Migration effort | Medium | Testing, potential debugging |

**Net Value**: The migration risk is not justified by zero cost savings.

## Original Rationale (Invalidated)

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Always use `ubuntu-latest` | Maximum compatibility, familiar | ~~60% more expensive than ARM~~ **Same cost (free)** | **Now preferred** |
| Always use Windows | PowerShell native support | Slower startup, compatibility | Unnecessary |
| Mixed without policy | Flexibility | Inconsistent, hard to maintain | No governance |
| Self-hosted runners | Full control, potentially free | Maintenance burden, security risk | Out of scope |

## Consequences of Rejection

### Positive

- Avoid unnecessary migration effort
- Maintain maximum compatibility with existing tools
- No risk of ARM-related breakage

### Negative

- Miss potential ~40% CPU performance improvement (unvalidated)

### Action Items

1. **Keep existing workflows on `ubuntu-latest`** - no migration needed
2. **Evaluate ARM for performance** - if workflow runtime is a bottleneck, test ARM on a per-workflow basis
3. **Document any ARM experiments** - track compatibility issues if ARM is tested

## References

- [GitHub Actions Pricing](https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions)
- [ARM Runner Free for Public Repos (Jan 2025)](https://github.blog/changelog/2025-01-16-linux-arm64-hosted-runners-now-available-for-free-in-public-repositories-public-preview/)
- [ARM Runner GA (Aug 2025)](https://github.blog/changelog/2025-08-07-arm64-hosted-runners-for-public-repositories-are-now-generally-available/)
- Session 38: Cost optimization discussion

---

*Template Version: 1.0*
*Created: 2025-12-20*
*Rejected: 2025-12-21*
