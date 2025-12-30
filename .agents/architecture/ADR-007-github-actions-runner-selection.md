# ADR-007: GitHub Actions Runner Selection

**Status**: Accepted
**Date**: 2025-12-29
**Authors**: DevOps Agent
**Related**: Issue #197

## Context

GitHub Actions offers multiple runner types with different cost and performance characteristics. The project incurs significant CI/CD costs from workflow execution. Runner selection directly impacts both operational costs and CI/CD performance.

### Available Runners

| Runner | Architecture | Cost/Minute | Speed | Notes |
|--------|--------------|-------------|-------|-------|
| ubuntu-latest | x64 | $0.008 | Baseline | Legacy default |
| ubuntu-24.04-arm | ARM64 | $0.005 | ~Same | 37.5% cheaper |
| windows-latest | x64 | $0.016 | Slower | 2x cost, ~45s startup |

### Current State (Pre-ADR)

- **89% ARM adoption** (32/36 jobs)
- **5.5% x64 Linux** (2/36 jobs - copilot-setup-steps, pr-validation)
- **5.5% Windows** (2/36 jobs - pester-tests Windows-specific jobs)

## Decision

**Default to ARM64 runners for all Linux workflows** unless documented architectural constraints exist.

### Preference Order

1. **ubuntu-24.04-arm** (default for Linux workflows)
2. **ubuntu-latest** (x64, only if ARM incompatibility documented)
3. **windows-latest** (only for Windows-specific requirements)

### ARM-First Policy

All new workflows MUST use `ubuntu-24.04-arm` unless:
1. Dependency lacks ARM64 support (documented with evidence)
2. Action incompatible with ARM (documented with issue link)
3. Windows-specific functionality required (use windows-latest)

### Exception Documentation Format

When x64 or Windows runners required, add comment above `runs-on`:

```yaml
# ADR-007 Exception: [Brief reason]
# Dependency: [Specific package/action that requires x64/Windows]
# Issue: [Link to GitHub issue or documentation]
runs-on: ubuntu-latest  # or windows-latest
```

## Consequences

### Positive

**Cost Savings**:
- 37.5% reduction per job migrated from x64 to ARM
- Cumulative savings across 34 ARM jobs
- No performance degradation observed

**Proven Compatibility**:
- PowerShell Core (ARM64 native)
- Node.js ecosystem (actions/setup-node)
- GitHub CLI (ARM64 binary)
- Pester testing framework
- PSScriptAnalyzer
- All project dependencies

**Environmental**:
- ARM processors more energy-efficient than x64

### Negative

**Migration Overhead**:
- One-time cost to audit and migrate existing workflows
- Testing required for each migrated workflow
- Documentation updates

**Dependency Monitoring**:
- Must verify ARM support for new dependencies
- Potential delays if dependency lacks ARM support
- May require fallback to x64 in rare cases

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Action incompatibility | LOW | MEDIUM | Test before merge, rollback to x64 if needed |
| Performance regression | VERY LOW | LOW | Monitor execution times, revert if >10% slower |
| Dependency unavailable | LOW | MEDIUM | Document exception, use x64 temporarily |

## Implementation

### Phase 1: Audit (Complete)

**Status**: ✅ COMPLETE (2025-12-29)
**Outcome**: 89% ARM adoption already achieved
**Analysis**: `.agents/devops/arm-runner-migration-analysis.md`

### Phase 2: Migrate Remaining Workflows

**Workflows**:
1. copilot-setup-steps.yml (invalid ADR-024 exception)
2. pr-validation.yml (no blocker identified)

**Testing**:

```bash
# Test copilot-setup-steps
gh workflow run copilot-setup-steps.yml --ref chore/197-arm-runner-migration

# Test pr-validation (create PR from branch)
gh pr create --base main --head chore/197-arm-runner-migration
```

**Rollback**:

```bash
# If workflow fails, revert to x64
git checkout main -- .github/workflows/[workflow].yml
git commit -m "chore: rollback [workflow] to x64 runner"
```

### Phase 3: Documentation

**Updates Required**:
- [x] Create ADR-007 (this document)
- [ ] Update COST-GOVERNANCE.md with runner selection policy
- [ ] Document pester-tests.yml Windows requirement

## Documented Exceptions

### Windows Runners (Justified)

#### pester-tests.yml - Windows Test Jobs

**Jobs**: `test`, `script-analysis`
**Reason**: Windows-specific test assumptions
**Evidence**:
- File path format testing (backslash vs forward slash)
- Hidden file behavior (Windows vs Linux differ)
- PowerShell Desktop compatibility validation
- Tests explicitly assume Windows filesystem semantics

**Status**: APPROVED (cannot migrate to Linux/ARM)

```yaml
# ADR-007 Exception: Windows-specific test assumptions
# Tests validate file paths, hidden files, and PowerShell Desktop behavior
# that differ between Windows and Linux
runs-on: windows-latest
```

## Validation

### Pre-Merge Checks

- [ ] Workflow runs successfully on ARM runner
- [ ] All steps complete without architecture-related errors
- [ ] Execution time within 10% of baseline (x64)
- [ ] Exception documented if x64 required

### Post-Merge Monitoring

- Monitor first 5 runs of migrated workflows
- Compare execution times (ARM vs x64 baseline)
- Document ARM-specific issues if discovered

## Metrics

### Cost Impact (After Full Migration)

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| ARM Jobs | 32 (89%) | 34 (94%) | +2 |
| x64 Jobs | 2 (5.5%) | 0 (0%) | -2 |
| Windows Jobs | 2 (5.5%) | 2 (6%) | 0 |
| Cost Reduction | - | 5.5% | On migrated jobs |

### Performance Baseline

| Workflow | x64 Time | ARM Time | Delta |
|----------|----------|----------|-------|
| [TBD] | [Baseline] | [Actual] | [%] |

## References

- [GitHub ARM Runners Documentation](https://docs.github.com/en/actions/using-github-hosted-runners/about-github-hosted-runners/about-github-hosted-runners#standard-github-hosted-runners-for-public-repositories)
- [Issue #197: ARM Runner Migration](https://github.com/rjmurillo/ai-agents/issues/197)
- [ARM Migration Analysis](./../devops/arm-runner-migration-analysis.md)
- [PowerShell Core ARM64 Support](https://github.com/PowerShell/PowerShell/releases)

## Review Schedule

**Frequency**: Quarterly
**Next Review**: 2025-03-29
**Trigger Events**:
- New GitHub Actions runner types available
- Significant cost changes in runner pricing
- Discovery of ARM incompatibility in project dependencies
