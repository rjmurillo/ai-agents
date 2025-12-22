# ADR-014: GitHub Actions Runner Selection

## Status

Accepted

## Context

GitHub Actions offers multiple runner types with varying costs and capabilities. Public repositories receive free minutes for x64 runners but incur costs for ARM runners. However, ARM runners offer significant cost savings through improved price per minute and better performance per dollar.

### Current State

All workflows use `ubuntu-latest` (x64) or `windows-latest` runners without cost optimization consideration.

### Runner Pricing (Public Repositories)

| Runner | Cost/Min | Performance | Use Case |
|--------|----------|-------------|----------|
| `ubuntu-latest` (x64) | $0.008 | Baseline | Default x64 workflows |
| `ubuntu-24.04-arm` | $0.005 | Better price/performance | ARM-compatible workloads |
| `windows-latest` | $0.016 | Required for Windows | Windows-specific needs |

### Cost Impact

Migrating ubuntu-latest workflows to ARM provides **37.5% cost savings** ($0.008 to $0.005 per minute).

For a project with 1000 minutes/month of Linux CI:
- x64 cost: $8.00/month
- ARM cost: $5.00/month
- **Savings: $3.00/month (37.5%)**

## Decision

**All GitHub Actions workflows MUST use `ubuntu-24.04-arm` runners unless documented ARM compatibility issues exist.**

### Runner Selection Policy

1. **Default**: `ubuntu-24.04-arm` for all Linux workflows
2. **Exception**: `windows-latest` for Windows-specific requirements (PowerShell on Windows, Windows-only tools)
3. **Documentation Required**: Any workflow using x64 runners MUST include an ADR-014 compliance comment explaining why

### Compliance Comment Format

Workflows using ARM runners:

```yaml
jobs:
  job-name:
    # ADR-014: ARM runner for cost optimization (37.5% savings vs x64)
    runs-on: ubuntu-24.04-arm
```

Workflows requiring Windows or macOS:

```yaml
jobs:
  job-name:
    # ADR-014 Exception: Windows/macOS runner required for [specific reason]
    # Issue: [Link to tracking issue or upstream limitation]
    runs-on: windows-latest  # or macos-latest
```

Workflows with ARM compatibility issues (if any):

```yaml
jobs:
  job-name:
    # ADR-014 Exception: [Specific tool/dependency] lacks ARM support
    # Issue: [Link to tracking issue or upstream limitation]
    runs-on: ubuntu-latest
```

## Rationale

### Cost Optimization

- **37.5% savings** on Linux runner minutes
- Scales with project growth
- No functional trade-offs for compatible workloads

### ARM Compatibility

Modern tooling supports ARM64:

- **GitHub Actions**: All official actions (checkout, setup-python, setup-node, upload-artifact, etc.) support ARM
- **PowerShell**: Cross-platform, runs on ARM Linux
- **Python**: Native ARM64 support (3.x)
- **Node.js**: Native ARM64 support (LTS versions)
- **Docker**: Multi-arch images widely available

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Keep `ubuntu-latest` | No migration effort | 37.5% higher cost | Cost not justified |
| Use self-hosted ARM | Lower long-term cost | Maintenance overhead, security responsibility | Managed runners preferred |
| Use `ubuntu-latest` conditionally | Flexibility | Inconsistent cost profile | Prefer default optimization |

### Trade-offs

**Accepted**:
- Small migration effort (1-2 line changes per workflow)
- Need to verify ARM compatibility (one-time check)

**Avoided**:
- 37.5% higher costs
- Missing optimization opportunity

## Consequences

### Positive

- **37.5% cost reduction** on Linux workflows
- Better performance per dollar
- Aligns with industry shift to ARM
- Forces conscious decisions about runner choice

### Negative

- Migration effort for existing workflows
- Need to document exceptions
- Potential ARM incompatibility discovery (edge cases)

### Neutral

- Workflow syntax changes minimal (runner line only)
- No functional changes for compatible workloads

## Implementation Notes

### Migration Checklist

For each workflow:

1. Identify current runner configuration
2. Test on `ubuntu-24.04-arm`
3. Add ADR-014 compliance comment
4. Update `runs-on:` line
5. Commit with rationale

### Testing Strategy

1. **Smoke Test**: Run workflow on ARM, verify success
2. **Functionality Test**: Verify outputs match x64 behavior
3. **Performance Test**: Compare execution time (expect comparable or better)

### Rollback Plan

If ARM compatibility issues arise:
1. Revert to `ubuntu-latest` for affected workflow
2. Add ADR-014 exception comment with issue link
3. Track upstream ARM support status
4. Re-evaluate quarterly

### Documentation Requirements

**Required for ALL workflows**:
- ADR-014 compliance comment explaining runner choice

**Required for exceptions**:
- Specific reason (tool name, ARM incompatibility details)
- Link to tracking issue or upstream limitation

## Related Decisions

- ADR-006: Thin Workflows, Testable Modules (workflow design principles)
- ADR-005: PowerShell-Only Scripting (PowerShell supports ARM Linux)

## References

- [GitHub ARM Runner Announcement](https://docs.github.com/en/actions/using-github-hosted-runners/about-github-hosted-runners/about-github-hosted-runners#standard-github-hosted-runners-for-public-repositories)
- [GitHub Actions Pricing](https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions)
- [ARM64 Ubuntu Support](https://ubuntu.com/download/server/arm)
- [PowerShell on ARM Linux](https://learn.microsoft.com/en-us/powershell/scripting/install/installing-powershell-on-linux)
