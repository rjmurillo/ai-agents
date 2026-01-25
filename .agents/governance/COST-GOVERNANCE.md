# Cost Governance

## Overview

This document outlines cost optimization policies and practices for the AI Agents project, focusing on GitHub Actions infrastructure costs.

## GitHub Actions Cost Policy

### Runner Selection (ADR-014)

**Policy**: All GitHub Actions workflows MUST use `ubuntu-24.04-arm` runners unless documented ARM compatibility issues exist.

**Cost Impact**:

| Runner Type | Cost/Min | Use Case | Status |
|-------------|----------|----------|--------|
| `ubuntu-24.04-arm` | $0.005 | Default for Linux workflows | **Preferred** |
| `ubuntu-latest` (x64) | $0.008 | ARM-incompatible workloads only | Exception only |
| `windows-latest` | $0.016 | Windows-specific requirements | Exception only |

**Savings**: 37.5% cost reduction on Linux workflows ($0.008 → $0.005 per minute)

**See**: [ADR-024: GitHub Actions Runner Selection](../architecture/ADR-024-github-actions-runner-selection.md)

### Current Implementation Status

**Migrated to ARM (22 jobs)**:

- agent-metrics.yml (2 jobs)
- ai-issue-triage.yml (1 job)
- ai-pr-quality-gate.yml (4 jobs)
- ai-session-protocol.yml (3 jobs)
- ai-spec-validation.yml (1 job)
- copilot-context-synthesis.yml (2 jobs)
- drift-detection.yml (1 job)
- pester-tests.yml (3 jobs: check-paths, test, skip-tests)
- validate-generated-agents.yml (1 job)
- validate-paths.yml (3 jobs)
- validate-planning-artifacts.yml (1 job)

**x64 Exceptions (1 job)**:

- copilot-setup-steps.yml (copilot-setup-steps job) - Must match Copilot agent architecture (x64) for dependency compatibility

### Compliance Requirements

**All workflows MUST include ADR-014 compliance comments**:

ARM runners:

```yaml
jobs:
  job-name:
    # ADR-014: ARM runner for cost optimization (37.5% savings vs x64)
    runs-on: ubuntu-24.04-arm
```

Windows exceptions:

```yaml
jobs:
  job-name:
    # ADR-014 Exception: Windows runner required for [specific reason]
    # Issue: [Link to tracking issue or upstream limitation]
    runs-on: windows-latest
```

x64 exceptions (if any):

```yaml
jobs:
  job-name:
    # ADR-014 Exception: [Tool/dependency name] lacks ARM support
    # Issue: [Link to tracking issue or upstream limitation]
    runs-on: ubuntu-latest
```

## Cost Monitoring

### Metrics to Track

1. **Monthly runner minutes** by type (ARM, x64, Windows)
2. **Cost per runner type**
3. **Workflow execution time trends**
4. **Failed workflow retry costs**

### Review Cadence

- **Monthly**: Review runner usage and costs
- **Quarterly**: Evaluate ARM compatibility of remaining x64 workloads
- **Annually**: Review runner selection policy against GitHub pricing changes

## Exception Process

### Requesting x64 or Windows Runners

When ARM runners cannot be used:

1. **Document the reason** in workflow with ADR-014 exception comment
2. **Link to evidence**:
   - Upstream issue for ARM support
   - Tool documentation stating x64/Windows requirement
   - Test results showing ARM incompatibility
3. **Create tracking issue** if tool is expected to add ARM support
4. **Re-evaluate quarterly** to migrate when possible

### Approval Requirements

- **Windows runners**: Automatic approval if Windows-specific functionality required
- **x64 runners**: Document ARM incompatibility with evidence
- **Self-hosted runners**: Requires architecture review (ADR process)

## Best Practices

### Workflow Optimization

1. **Cache dependencies** to reduce execution time
2. **Use path filters** to skip unnecessary runs
3. **Parallelize independent jobs** for faster feedback
4. **Set appropriate timeouts** to prevent runaway costs
5. **Use artifact retention policies** to limit storage costs

### ARM Compatibility Verification

Before migrating to ARM:

1. **Check tool ARM support**:
   - GitHub official actions (all ARM-compatible)
   - Python packages (verify ARM64 wheels available)
   - Node.js packages (verify ARM64 support)
   - Docker images (verify multi-arch or ARM64 images exist)
2. **Test locally** on ARM64 Linux if available
3. **Test in PR** before merging
4. **Monitor first runs** for performance/compatibility issues

## Cost Optimization Wins

### Completed Initiatives

| Initiative | Impact | Status |
|------------|--------|--------|
| ARM Runner Migration | 37.5% reduction on Linux workflows | ✅ Complete |

### Planned Initiatives

| Initiative | Target Date | Expected Impact |
|------------|-------------|-----------------|
| Workflow path filter optimization | Q1 2026 | 20-30% reduction in unnecessary runs |
| Dependency caching improvements | Q1 2026 | 10-15% execution time reduction |

## References

- [ADR-024: GitHub Actions Runner Selection](../architecture/ADR-024-github-actions-runner-selection.md)
- [GitHub Actions Pricing](https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions)
- [GitHub ARM Runners Documentation](https://docs.github.com/en/actions/using-github-hosted-runners/about-github-hosted-runners/about-github-hosted-runners#standard-github-hosted-runners-for-public-repositories)
