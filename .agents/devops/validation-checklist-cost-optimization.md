# GitHub Actions Cost Optimization - Validation Checklist

## Post-Deployment Validation

Use this checklist to validate the cost optimization changes are working correctly.

## ARM Runner Compatibility

Monitor the first few workflow runs for each migrated workflow to ensure ARM compatibility.

### Workflows to Monitor

- [ ] **agent-metrics.yml** - Python scripts on ARM
- [ ] **ai-issue-triage.yml** - GitHub CLI and PowerShell on ARM
- [ ] **ai-pr-quality-gate.yml** - AI review actions on ARM
- [ ] **ai-session-protocol.yml** - Session validation on ARM
- [ ] **ai-spec-validation.yml** - Spec validation on ARM
- [ ] **copilot-context-synthesis.yml** - Context synthesis on ARM
- [ ] **copilot-setup-steps.yml** - Node.js and PowerShell on ARM
- [ ] **drift-detection.yml** - PowerShell drift detection on ARM
- [ ] **label-issues.yml** - GitHub Actions script on ARM
- [ ] **label-pr.yml** - Actions labeler on ARM
- [ ] **pester-tests.yml** (check-paths, skip-tests jobs) - Path checking on ARM
- [ ] **validate-paths.yml** - PowerShell validation on ARM
- [ ] **validate-planning-artifacts.yml** - PowerShell validation on ARM

### Known ARM Incompatibilities

If you encounter ARM-specific issues, document them here:

- None identified yet

### Rollback Procedure

If a workflow fails due to ARM incompatibility:

1. Create hotfix PR reverting that specific workflow to `ubuntu-latest`
2. Document the incompatibility in this file
3. Create issue to investigate ARM-compatible alternative
4. Update ADR-014 with documented exception

## Path Filter Validation

Verify path filters don't create false negatives (workflows not running when they should).

### Path Filter Test Cases

Test these scenarios to ensure path filters work correctly:

#### agent-metrics.yml

- [ ] Runs when `.claude/skills/metrics/**` changed
- [ ] Runs when `.github/workflows/agent-metrics.yml` changed
- [ ] Skips when only `.md` files changed
- [ ] Manual trigger (`workflow_dispatch`) works

#### copilot-setup-steps.yml

- [ ] Runs when `.githooks/**` changed
- [ ] Runs when `.github/workflows/copilot-setup-steps.yml` changed
- [ ] Skips when unrelated files changed
- [ ] Manual trigger works

#### drift-detection.yml

- [ ] Runs when `src/claude/**` changed
- [ ] Runs when `templates/agents/**` changed
- [ ] Runs when `build/scripts/Detect-AgentDrift.ps1` changed
- [ ] Runs when `.github/workflows/drift-detection.yml` changed
- [ ] Skips when unrelated files changed
- [ ] Manual trigger works

#### pester-tests.yml

- [ ] Runs when `scripts/**` changed
- [ ] Runs when `build/**` changed
- [ ] Runs when `.github/scripts/**` changed
- [ ] Runs when `.claude/skills/**` changed
- [ ] Runs when `tests/**` changed
- [ ] Runs when `.github/workflows/pester-tests.yml` changed
- [ ] Skips when only `.md` files changed
- [ ] Manual trigger works

### False Negative Detection

If a workflow should have run but didn't:

1. Identify the file change that should have triggered it
2. Update the path filter to include that path pattern
3. Document the case in ADR-016
4. Consider if the filter is too restrictive

## Concurrency Group Validation

Verify concurrency groups cancel duplicate runs as expected.

### Expected Behavior

#### Branch/PR Workflows (cancel-in-progress: true)

Test by making rapid commits to a PR:

- [ ] **agent-metrics.yml** - New commits cancel previous runs
- [ ] **ai-pr-quality-gate.yml** - New PR commits cancel previous reviews
- [ ] **ai-session-protocol.yml** - New session changes cancel previous validations
- [ ] **copilot-setup-steps.yml** - New setup triggers cancel previous runs
- [ ] **drift-detection.yml** - New drift checks cancel previous runs
- [ ] **pester-tests.yml** - New commits cancel previous test runs
- [ ] **validate-generated-agents.yml** - New changes cancel previous validations
- [ ] **validate-paths.yml** - New changes cancel previous validations
- [ ] **validate-planning-artifacts.yml** - New changes cancel previous validations

#### Issue-Based Workflows (cancel-in-progress: false)

Test by updating the same issue multiple times:

- [ ] **ai-issue-triage.yml** - Multiple triage runs complete independently
- [ ] **copilot-context-synthesis.yml** - Multiple synthesis runs complete independently

### Concurrency Issues

If workflows are cancelling when they shouldn't:

1. Check the concurrency group formula
2. Verify `cancel-in-progress` setting is appropriate
3. Update ADR-016 with findings

## Artifact Retention Validation

Verify artifacts are deleted after the new retention period.

### Retention Period Checks

- [ ] **agent-metrics.yml** - Artifacts deleted after 7 days (check after 2025-12-29)
- [ ] **pester-tests.yml** - Artifacts deleted after 7 days (check after 2025-12-29)

### Artifact Cleanup

Manually verify in GitHub UI:
1. Navigate to Actions tab
2. Select a completed workflow run
3. Check artifact retention period displayed

## Cost Monitoring

Track actual cost reduction against projections.

### Weekly Cost Checks

Week 1 (2025-12-22 to 2025-12-29):
- [ ] Review workflow minutes used
- [ ] Check for ARM-related failures
- [ ] Verify path filters are working
- [ ] Estimated cost: $___

Week 2 (2025-12-29 to 2026-01-05):
- [ ] Review workflow minutes used
- [ ] Artifact deletions starting (7-day retention)
- [ ] Estimated cost: $___

Week 3 (2026-01-05 to 2026-01-12):
- [ ] Review workflow minutes used
- [ ] Validate artifact storage savings
- [ ] Estimated cost: $___

Week 4 (2026-01-12 to 2026-01-19):
- [ ] Review full month projection
- [ ] Compare to $100 target
- [ ] Estimated cost: $___

### Monthly Cost Review (End of January 2026)

- [ ] Total cost for January 2026: $___
- [ ] Compare to December 2025 baseline ($243.55)
- [ ] Actual savings: $___
- [ ] Projected annual savings: $___
- [ ] On track for <$100/month target? ☐ Yes ☐ No

### Cost Variance Analysis

If costs are higher than projected:

| Category | Projected | Actual | Variance | Reason |
|----------|-----------|--------|----------|--------|
| Workflow minutes | | | | |
| Artifact storage | | | | |
| Other | | | | |

## Issue Tracking

Create GitHub issues for any problems discovered:

- [ ] ARM compatibility issues: #___
- [ ] Path filter false negatives: #___
- [ ] Concurrency group problems: #___
- [ ] Cost variance investigation: #___

## Sign-Off

Once validation is complete, sign off here:

- [ ] ARM migration validated (no critical failures)
- [ ] Path filters validated (no false negatives)
- [ ] Concurrency groups validated (behaving correctly)
- [ ] Artifact retention validated (cleanup working)
- [ ] Cost reduction validated (on track for target)

**Validated by**: _______________
**Date**: _______________
**Monthly cost achieved**: $_____
