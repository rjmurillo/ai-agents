---
id: ADR-055
status: accepted
date: 2025-12-29
decision-makers: []
supersedes: [ADR-024, ADR-025]
superseded-by: null
explainer: null
implemented: false
---

# ADR-055: GitHub Actions Runner Selection

## Provenance

**Duplicate title and slug.** ADR-024 carries the identical title "GitHub Actions Runner Selection" and the identical filename slug `github-actions-runner-selection`. The duplication is an artifact, not a design. Verified history for this file: it has a single commit, `3e24d2c0`, from PR #1604 on 2026-04-10, whose message is "fix(adr): renumber duplicate ADR-032 and ADR-051 to ADR-055 and ADR-056". This record was **ADR-032** until that day, colliding with `ADR-032-ears-requirements-syntax.md`. Neither file is renamed now, because inbound citations resolve by path and a rename breaks every one of them. This record is the live runner-selection decision; ADR-024 is retired.

**Why this batch flipped some records and not others.** ADR-042 moved to `status: accepted` in the same campaign because a six-role debate log for it predates the change by seven months. Six records (ADR-075, ADR-077, ADR-078, ADR-089, ADR-093, ADR-098) carry `implemented: true` against `status: proposed` and were deliberately left alone: each has a debate log that explicitly withholds acceptance, and ADR-098 states the pair is intentional. ADR-042 is not precedent for flipping them.

**Exception marker.** This record prescribes `# ADR-055 Exception:`. It previously prescribed `# ADR-032 Exception:`. That was not a typo: this file WAS ADR-032, so the marker was correct until PR #1604 renamed the file to ADR-055 on 2026-04-10 and swept the filename without sweeping the body. The number then silently came to mean `ADR-032-ears-requirements-syntax.md`, an unrelated decision. The root cause is a rename with no in-body reference sweep, and no gate checks that a record's self-references match its current number; PR #1604's own remediation notes describe that sweep as a manual `git grep`. Two further spellings are loose in the tree, `# ADR-024 Exception:` and `# ADR-014 Exception:`, from the separate lineage of ADR-024 (accepted as ADR-014, renumbered to ADR-024 by PR #476 on 2025-12-29). Both are void as markers. Neither points where it reads: ADR-024 is the runner record this one retires, and **ADR-014 today is `Distributed Handoff Architecture`, which is accepted, live, and unrelated to runners** (`.claude/rules/universal.md` MUST-3 still binds it). A reader who follows `# ADR-014 Exception:` to its number lands on the handoff decision. Existing markers outside this file still carry retired spellings and are tracked for migration in issue #5199. The `# ADR-055 Exception:` spelling is **new**, not a restoration: no marker in this spelling exists anywhere in the tree today, and no validator reads the pattern. Retiring three spellings and minting a fourth is a convention change, not a transcription of an existing one, and it is recorded here so the next reader does not mistake it for one.

**Authors**: DevOps Agent
**Related**: Issue #197, Issue #5192, Issue #5199

## Date

2025-12-29

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
# ADR-055 Exception: [Brief reason]
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
- [x] Create this document (numbered ADR-032 at the time; renumbered to ADR-055 by PR #1604 on 2026-04-10)
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
# ADR-055 Exception: Windows-specific test assumptions
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

The `0 (0%)` figure was the 2025-12-29 measurement and no longer holds. Measured 2026-08-21 across
`.github/workflows/*.yml`: 111 of 132 `runs-on` declarations are `ubuntu-24.04-arm`, leaving 21
non-ARM declarations (10 `ubuntu-latest`, 5 `${{ matrix.os }}`, 4 `ubuntu-24.04`, 2 `windows-latest`).
**None of the 21 carries an exception marker in any spelling.** The ARM-first preference is in force;
the exception-documentation requirement in this record is not. Tracked in issue #5199.
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
**Next Review**: not set. The date recorded here read `2025-03-29`, nine months before this record's own
2025-12-29 decision date, so it was never a real schedule and no review ever fired against it. Setting a
true date is an owner decision; the optional `review-by` frontmatter field added in this campaign is
where it belongs once chosen.
**Trigger Events**:
- New GitHub Actions runner types available
- Significant cost changes in runner pricing
- Discovery of ARM incompatibility in project dependencies
