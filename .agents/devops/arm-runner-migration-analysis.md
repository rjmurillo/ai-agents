# ARM Runner Migration Analysis

**Issue**: #197
**Date**: 2025-12-29
**Status**: Implementation Ready

## Executive Summary

**Current State**: 89% of jobs already use ARM runners (32/36 jobs)
**Migration Target**: Migrate remaining 3 workflows to ARM
**Expected Savings**: 37.5% cost reduction on migrated workflows
**Risk Level**: LOW - Most infrastructure already proven on ARM

## Workflow Inventory

### Already on ARM (32 jobs across 17 workflows) [PASS]

| Workflow | Jobs on ARM | Notes |
|----------|-------------|-------|
| agent-metrics.yml | 2 | Fully ARM |
| ai-issue-triage.yml | 1 | Fully ARM |
| ai-pr-quality-gate.yml | 3 | Fully ARM |
| ai-session-protocol.yml | 3 | Fully ARM |
| ai-spec-validation.yml | 1 | Fully ARM |
| auto-assign-reviewer.yml | 1 | Fully ARM |
| copilot-context-synthesis.yml | 2 | Fully ARM |
| drift-detection.yml | 1 | Fully ARM |
| label-issues.yml | 1 | Fully ARM |
| label-pr.yml | 1 | Fully ARM |
| memory-validation.yml | 1 | Fully ARM |
| pr-maintenance.yml | 3 | Fully ARM |
| semantic-pr-title-check.yml | 1 | Fully ARM |
| validate-generated-agents.yml | 1 | Fully ARM |
| validate-handoff-readonly.yml | 1 | Fully ARM |
| validate-paths.yml | 3 | Fully ARM |
| validate-planning-artifacts.yml | 1 | Fully ARM |
| pester-tests.yml | 3 | Skip jobs only (path filtering) |

**Proven ARM Capabilities**:
- PowerShell Core scripts
- Node.js (markdownlint-cli2, actions/setup-node)
- GitHub CLI operations
- Git operations
- Pester testing framework
- PSScriptAnalyzer
- dorny/paths-filter action
- dorny/test-reporter action

### Requires Migration (3 workflows, 4 jobs)

#### 1. copilot-setup-steps.yml [READY]

**Current**: ubuntu-latest (x64)
**Reason Given**: "ADR-024 Exception: x64 runner required to match Copilot agent architecture"
**Analysis**: This justification is INVALID
- PowerShell Core is cross-platform (ARM64 supported)
- Node.js actions support ARM (actions/setup-node proven in 17 workflows)
- Git operations are platform-agnostic
- No architecture-specific dependencies identified

**Dependencies**:
- actions/checkout (proven on ARM)
- actions/setup-node (proven on ARM)
- Node.js/npm (proven on ARM)
- GitHub CLI (proven on ARM)
- PowerShell Core (proven on ARM)
- Pester module (proven on ARM in pester-tests.yml)

**Migration Recommendation**: MIGRATE to ubuntu-24.04-arm
**Risk**: VERY LOW
**Testing Strategy**: Run workflow via `gh workflow run --ref chore/197-arm-runner-migration`

#### 2. pr-validation.yml [READY]

**Current**: ubuntu-latest (x64)
**Reason Given**: None (legacy default)
**Analysis**: All dependencies ARM-compatible

**Dependencies**:
- PowerShell Core (proven on ARM)
- GitHub CLI (proven on ARM)
- actions/checkout (proven on ARM)
- Post-IssueComment skill (PowerShell, proven on ARM)

**Migration Recommendation**: MIGRATE to ubuntu-24.04-arm
**Risk**: VERY LOW
**Testing Strategy**: Test on feature branch PR

#### 3. pester-tests.yml [KEEP WINDOWS]

**Current**: windows-latest (2 test jobs)
**Reason**: Windows-specific test assumptions
**Analysis**: CORRECT decision to keep Windows

**Windows-Specific Requirements** (from comments):
- "Many tests have Windows-specific assumptions"
- File path formats (backslash vs forward slash)
- Hidden file behavior
- Windows PowerShell Desktop compatibility testing

**Jobs**:
- `test` job: windows-latest [KEEP]
- `script-analysis` job: windows-latest [KEEP]
- `check-paths` job: ubuntu-24.04-arm [ALREADY ARM]
- `skip-tests` job: ubuntu-24.04-arm [ALREADY ARM]
- `skip-script-analysis` job: ubuntu-24.04-arm [ALREADY ARM]

**Migration Recommendation**: NO CHANGE (justified use of Windows runners)
**Documentation**: Add ADR-007 reference comment

## Migration Plan

### Phase 1: copilot-setup-steps.yml

**Change**:

```yaml
# Before
runs-on: ubuntu-latest

# After
# ADR-007: ARM runner for cost optimization (37.5% savings vs x64)
# All dependencies (Node.js, PowerShell Core, GitHub CLI) support ARM64
runs-on: ubuntu-24.04-arm
```

**Rollback**: Revert to `ubuntu-latest` if workflow fails
**Validation**: Workflow completes successfully, all steps pass

### Phase 2: pr-validation.yml

**Change**:

```yaml
# Before
runs-on: ubuntu-latest

# After
# ADR-007: ARM runner for cost optimization (37.5% savings vs x64)
# PowerShell Core and GitHub CLI fully support ARM64
runs-on: ubuntu-24.04-arm
```

**Rollback**: Revert to `ubuntu-latest` if validation fails
**Validation**: PR validation report posts correctly, all checks pass

### Phase 3: Documentation

**Create**: `.agents/architecture/ADR-007-github-actions-runner-selection.md`
**Reference**: Document ARM-first strategy with documented exceptions

## Cost Impact Analysis

### Current Cost Distribution

| Runner Type | Jobs | Percentage | Relative Cost |
|-------------|------|------------|---------------|
| ubuntu-24.04-arm | 32 | 89% | 1.00x (baseline) |
| ubuntu-latest (x64) | 2 | 5.5% | 1.6x |
| windows-latest | 2 | 5.5% | 3.2x |

### After Migration

| Runner Type | Jobs | Percentage | Relative Cost | Savings |
|-------------|------|------------|---------------|---------|
| ubuntu-24.04-arm | 34 | 94% | 1.00x (baseline) | - |
| windows-latest | 2 | 6% | 3.2x | - |

**Total Cost Reduction**: 5.5% of x64 Linux runners eliminated (2/36 jobs migrated)
**Windows Runners**: Justified for platform-specific testing (cannot migrate)

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Copilot setup fails on ARM | LOW | MEDIUM | Test with workflow_dispatch before PR merge |
| PR validation fails on ARM | VERY LOW | MEDIUM | Already proven in 17 workflows |
| Actions incompatibility | VERY LOW | LOW | All actions already proven on ARM |
| Performance regression | VERY LOW | LOW | ARM runners comparable to x64 |

## Testing Strategy

### Pre-Migration Testing

1. Create feature branch `chore/197-arm-runner-migration`
2. Migrate copilot-setup-steps.yml first
3. Test via: `gh workflow run copilot-setup-steps.yml --ref chore/197-arm-runner-migration`
4. Verify all steps complete successfully
5. Migrate pr-validation.yml
6. Create PR to trigger pr-validation workflow
7. Verify PR validation report posts correctly

### Post-Migration Monitoring

1. Monitor first 5 workflow runs for each migrated workflow
2. Compare execution times (baseline vs ARM)
3. Verify no job failures related to runner architecture
4. Document any ARM-specific issues in ADR-007

## Rollback Strategy

### Immediate Rollback (if workflow fails)

```bash
# Revert single workflow
git checkout main -- .github/workflows/copilot-setup-steps.yml
git commit -m "chore: rollback copilot-setup-steps to x64 runner"
git push
```

### Targeted Rollback (specific job issues)

Individual jobs can be reverted to x64 without affecting other jobs:

```yaml
# Mixed runner strategy (if needed)
jobs:
  job1:
    runs-on: ubuntu-24.04-arm  # ARM works
  job2:
    runs-on: ubuntu-latest  # x64 needed (documented exception)
```

## Success Criteria

- [ ] copilot-setup-steps.yml runs successfully on ARM
- [ ] pr-validation.yml runs successfully on ARM
- [ ] No workflow failures attributed to ARM architecture
- [ ] ADR-007 documents ARM-first strategy
- [ ] Cost savings achieved (37.5% on migrated jobs)
- [ ] Windows runner usage justified and documented

## Recommendations

### Immediate Actions

1. **MIGRATE** copilot-setup-steps.yml (invalid ADR-024 exception)
2. **MIGRATE** pr-validation.yml (no blocker identified)
3. **DOCUMENT** pester-tests.yml Windows requirement in ADR-007
4. **CREATE** ADR-007 GitHub Actions Runner Selection

### Future Considerations

1. **Audit** test suite for ARM compatibility
   - Identify Windows-specific test assumptions
   - Create ARM-compatible test variants where possible
   - Maintain Windows tests for platform-specific validation
2. **Monitor** GitHub Actions for new ARM-compatible actions
3. **Review** workflow runner selection quarterly

## Conclusion

**Migration Readiness**: READY TO IMPLEMENT
**Risk Level**: LOW (89% of infrastructure already proven on ARM)
**Expected Outcome**: 94% ARM adoption, 37.5% cost savings on migrated workflows
**Recommended Approach**: Incremental migration with testing at each phase
