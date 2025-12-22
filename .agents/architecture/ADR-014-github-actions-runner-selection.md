# ADR-014: GitHub Actions Runner Selection

## Status

Accepted

## Context

GitHub Actions offers multiple runner types with varying costs and capabilities. ARM runners provide significant advantages beyond cost optimization: native architecture performance, faster build cycles, true multi-arch support, ecosystem alignment, and improved power efficiency.

### Current State

All workflows use `ubuntu-latest` (x64) or `windows-latest` runners without optimization consideration.

### Benefits of ARM Runners

**1. Cost Optimization**

ARM runners offer 37.5% cost savings ($0.008 → $0.005 per minute).

For a project with 1000 minutes/month of Linux CI:
- x64 cost: $8.00/month
- ARM cost: $5.00/month
- **Savings: $3.00/month (37.5%)**

**2. Native Architecture Performance**

For projects targeting ARM platforms (cloud, edge, IoT, mobile, Apple Silicon, multi-arch containers), running CI on native ARM hardware eliminates cross-compilation overhead and QEMU emulation that x64 runners would require. This produces faster builds and more accurate test results for ARM binaries.

**3. Faster Build/Test Cycles**

Real-world benchmarks show significant speedups for ARM workloads compared to x64 runners, with some builds reducing from 30+ minutes to ~4 minutes ([GitHub Actions ARM64 announcement](https://github.blog/changelog/2024-09-03-github-actions-arm64-linux-and-windows-runners-are-now-generally-available/)).

**4. True Multi-Arch CI/CD Support**

For products supporting multiple architectures (e.g., `linux/amd64` and `linux/arm64`), having both ARM and x64 runners enables:
- Parallel execution for each architecture
- Native build and validation per target platform
- Detection of subtle issues that only appear on real ARM execution (cross-compile + test on x64 alone can miss these)

**5. Ecosystem Alignment**

ARM is pervasive across modern infrastructure:
- Apple Silicon (macOS development)
- Edge/IoT hardware
- Cloud ARM servers (AWS Graviton, Azure Cobalt, Google Axion)
- Mobile devices

Using ARM runners aligns CI with where code actually runs in production.

**6. Power Efficiency and Sustainability**

ARM hardware typically consumes less power for similar workloads. While cost-per-minute may not be the deciding factor for public repositories (free minutes), power-to-performance ratio and reduced energy footprint support corporate sustainability goals.

### Runner Pricing (Public Repositories)

| Runner | Cost/Min | Performance | Use Case |
|--------|----------|-------------|----------|
| `ubuntu-latest` (x64) | $0.008 | Baseline | Default x64 workflows |
| `ubuntu-24.04-arm` | $0.005 | Better price/performance | ARM-compatible workloads |
| `windows-latest` | $0.016 | Required for Windows | Windows-specific needs |

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
