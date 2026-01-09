# Plan Critique: Milestone Tracking Automation

**Date**: 2026-01-09
**Branch**: feat/milestone-backstop
**Reviewer**: Critic Agent
**Files Reviewed**:
- `.github/workflows/milestone-tracking.yml`
- `scripts/Get-LatestSemanticMilestone.ps1`
- `scripts/Set-ItemMilestone.ps1`
- `tests/Get-LatestSemanticMilestone.Tests.ps1`
- `tests/Set-ItemMilestone.Tests.ps1`

## Verdict

**NEEDS REVISION**

## Summary

The implementation demonstrates solid engineering with PowerShell delegation, exit code standardization per ADR-035, and thin workflow pattern per ADR-006. However, critical architectural decisions require validation, and edge cases remain unhandled. The semantic version auto-detection introduces flexibility at the cost of convention dependency risk.

## Strengths

1. **ADR compliance**: PowerShell-only (ADR-005), thin workflows (ADR-006), exit codes (ADR-035)
2. **Testability**: All logic in PowerShell scripts with Pester coverage
3. **DRY principle**: Delegates to existing Set-IssueMilestone.ps1 skill
4. **Error handling**: Comprehensive exit codes, structured output to GITHUB_OUTPUT
5. **Step summaries**: Clear CI feedback with formatted results
6. **Version comparison**: Uses [System.Version] for proper sorting (0.10.0 > 0.3.0)
7. **Idempotency**: Skip logic preserves manual milestone assignments
8. **Comprehensive testing**: Both unit and integration test structures present

## Issues Found

### Critical (Must Fix)

#### 1. Untested Delegation to Set-IssueMilestone.ps1

**Location**: `Set-ItemMilestone.ps1:194-213`

**Issue**: Script delegates to Set-IssueMilestone.ps1 but tests mock this invocation instead of verifying actual behavior. The delegation pattern is untested end-to-end.

**Evidence**: Test file line 79-88 contains comment "integration tests would verify end-to-end behavior" acknowledging gap.

**Risk**: Set-IssueMilestone.ps1 exit code 5 (has milestone without -Force) conflicts with Set-ItemMilestone.ps1 skip logic. Orchestration script checks milestone existence first, but skill also checks. Redundant validation creates two failure paths for same condition.

**Recommendation**: Either:
- Add integration tests verifying Set-IssueMilestone.ps1 behavior
- OR refactor Set-ItemMilestone.ps1 to call skill with -Force (skill handles skip logic)
- OR document rationale for double-check pattern (defense in depth)

**Data**: Set-IssueMilestone.ps1 line 111-113 exits with code 5 if milestone exists without -Force. Set-ItemMilestone.ps1 lines 155-171 pre-checks milestone existence and skips.

#### 2. No Fallback Strategy When No Semantic Milestones Exist

**Location**: `Get-LatestSemanticMilestone.ps1:128-161`, `Set-ItemMilestone.ps1:185-187`

**Issue**: If repository has zero semantic version milestones (only "Future", "Backlog", etc.), workflow fails with exit code 2. No graceful degradation or actionable recovery path for maintainers.

**Evidence**: Detection script line 121, 160 exits with code 2. Step summary says "Create a semantic version milestone" but doesn't provide automation.

**Risk**: New repositories without semantic milestones cannot use this workflow until manual milestone creation. Adoption friction for teams.

**Recommendation**: Add one of:
- `-CreateIfMissing` parameter to auto-create "0.1.0" milestone
- `-FallbackMilestone` parameter to use specific non-semantic milestone
- Document in workflow README that semantic milestone is prerequisite
- Fail workflow gracefully (exit 0 with skip) instead of error

**Quantified impact**: Every new repo adopting this pattern requires manual milestone setup (5-10 minutes per repo, non-automated).

#### 3. Race Condition with Concurrent Workflow Runs

**Location**: `.github/workflows/milestone-tracking.yml:6-9`

**Issue**: Workflow triggers on PR close and issue close. If PR close also closes linked issue (common pattern), two workflow runs execute concurrently, both querying milestones and assigning. No concurrency control.

**Evidence**: Workflow lines 6-9 trigger on both events independently. GitHub Actions runs workflows in parallel by default.

**Risk**: API rate limit exhaustion, duplicate API calls, potential inconsistent state if milestone changes between query and assignment.

**Recommendation**: Add concurrency control to workflow:

```yaml
concurrency:
  group: milestone-tracking-${{ github.event.issue.number || github.event.pull_request.number }}
  cancel-in-progress: false
```

This serializes runs per item number, preventing races.

**Data**: GitHub Actions default concurrency is unlimited. Milestone query + assignment = 3 API calls per run. Two concurrent runs = 6 calls for same outcome.

### Important (Should Fix)

#### 4. Missing -Force Parameter for Override Scenarios

**Location**: `Set-ItemMilestone.ps1:26-28`, design decision question 2

**Issue**: Skip logic preserves manual assignments (good for normal operation) but provides no mechanism to force-update milestones when needed. Maintainer cannot override without manual GitHub UI action.

**Use case**: Bulk milestone migration (e.g., move all items from "0.2.0" to "0.3.0") requires manual reassignment per item.

**Recommendation**: Add `-Force` parameter to Set-ItemMilestone.ps1:

```powershell
[Parameter()]
[switch]$Force
```

Then pass to Set-IssueMilestone.ps1 call (line 204). Document usage for bulk operations.

**Effort**: <15 lines of code, 1 test case addition.

#### 5. Detection Script Location Violates Separation of Concerns

**Location**: `scripts/Get-LatestSemanticMilestone.ps1`, design decision question 3

**Issue**: Script is general-purpose (queries repository state) but lives in `scripts/` (workflow-specific location per thin-workflows pattern). Should be a reusable skill.

**Evidence**: Memory `pattern-thin-workflows` states:
- `.github/scripts/` - Workflow-specific logic (low reusability)
- `.claude/skills/github/` - Reusable GitHub operations (high reusability)

Milestone detection is reusable across repositories.

**Recommendation**: Move to `.claude/skills/github/scripts/milestone/Get-LatestSemanticMilestone.ps1` and update imports. This enables reuse by other workflows or manual invocation.

**Maintenance burden**: Current location implies workflow ownership, discouraging reuse.

#### 6. Test Coverage Gaps in Mock Fidelity

**Location**: `tests/Set-ItemMilestone.Tests.ps1:32-89`, `tests/Set-ItemMilestone.Tests.ps1:117-141`

**Issue**: Tests use complex mocking (`Test-Path`, `Get-ChildItem`) to simulate script presence but never verify actual script invocations with correct parameters. Mock fidelity is low for integration validation.

**Evidence**: Test line 82 comment acknowledges "integration tests would verify end-to-end behavior". Current tests verify query logic only.

**Recommendation**: Add contract tests using actual scripts in isolated test harness:

```powershell
Context "Integration with Get-LatestSemanticMilestone" {
    It "Passes correct parameters to detection script" {
        # Invoke Set-ItemMilestone with trace logging
        # Verify Get-LatestSemanticMilestone received Owner/Repo
    }
}
```

This validates parameter passing, script invocation, exit code propagation.

**Effort**: 3-5 test cases, ~50 lines of code.

#### 7. No Workflow Run Cost Analysis

**Location**: `.github/workflows/milestone-tracking.yml:18`, design decision question 5

**Issue**: Workflow runs on ARM runner (ADR-025 cost optimization) for all branches. No data on actual cost impact vs. benefit filtering.

**Question**: Is milestone tracking on feature branch PRs worth cost? Merged feature PRs typically don't need milestones until main merge.

**Recommendation**: Analyze workflow run frequency:

```bash
gh api /repos/rjmurillo/ai-agents/actions/workflows/milestone-tracking.yml/runs \
  --jq '.workflow_runs | group_by(.head_branch) | map({branch: .[0].head_branch, count: length})'
```

If >80% of runs are non-main branches, filter workflow to `main` only:

```yaml
if: |
  ((github.event_name == 'pull_request' && github.event.pull_request.merged == true && github.event.pull_request.base.ref == 'main') ||
   (github.event_name == 'issues' && github.event.issue.state == 'closed'))
```

**Data needed**: Workflow run count per branch (30 days).

#### 8. Semantic Version Pattern Too Restrictive

**Location**: `Get-LatestSemanticMilestone.ps1:125`

**Issue**: Regex `^\d+\.\d+\.\d+$` only matches X.Y.Z format. Does not support semantic version extensions like "1.0.0-beta", "2.0.0-rc.1".

**Risk**: If team adopts pre-release milestones for release candidates, detection fails.

**Recommendation**: Make pattern configurable via parameter:

```powershell
[Parameter()]
[string]$VersionPattern = '^\d+\.\d+\.\d+$'
```

Document supported patterns:
- Basic: `^\d+\.\d+\.\d+$` (default)
- Pre-release: `^\d+\.\d+\.\d+(-[a-zA-Z0-9\.]+)?$`
- Build metadata: `^\d+\.\d+\.\d+(\+[a-zA-Z0-9\.]+)?$`

**Effort**: 5 lines of code, 2 test cases.

### Minor (Consider)

#### 9. GITHUB_OUTPUT Format Not Validated

**Location**: `Get-LatestSemanticMilestone.ps1:179-182`, `Set-ItemMilestone.ps1:108-113`

**Issue**: Scripts write to GITHUB_OUTPUT but do not validate file existence or write success. Silent failures possible if environment variable is unset or file is read-only.

**Recommendation**: Add write validation:

```powershell
if ($env:GITHUB_OUTPUT) {
    try {
        "milestone_title=$($latest.title)" | Out-File $env:GITHUB_OUTPUT -Append -Encoding utf8
        if ($LASTEXITCODE -ne 0) { Write-Warning "Failed to write GITHUB_OUTPUT" }
    } catch {
        Write-Warning "GITHUB_OUTPUT write error: $_"
    }
}
```

**Benefit**: CI logs show clear warnings if output mechanism fails.

#### 10. No Rate Limit Handling

**Location**: `Get-LatestSemanticMilestone.ps1:85-88`

**Issue**: Script calls GitHub API without rate limit checks. If rate limit is exhausted, workflow fails with generic error.

**Recommendation**: Add pre-flight rate limit check using GitHubCore.psm1 function (if exists) or inline check:

```powershell
$rateLimitJson = gh api rate_limit 2>&1
if ($LASTEXITCODE -eq 0) {
    $rateLimit = $rateLimitJson | ConvertFrom-Json
    if ($rateLimit.rate.remaining -lt 10) {
        Write-Warning "Low rate limit: $($rateLimit.rate.remaining) remaining"
    }
}
```

**Effort**: 10 lines of code.

#### 11. Step Summary Markdown Injection Risk

**Location**: `Get-LatestSemanticMilestone.ps1:145`, `Set-ItemMilestone.ps1:129`

**Issue**: Step summary includes milestone titles from API without sanitization. If milestone title contains markdown characters (e.g., "v1.0.0 `code`"), formatting breaks.

**Risk**: Low (milestone titles are maintainer-controlled, not user input), but violates defense-in-depth.

**Recommendation**: Escape markdown special characters:

```powershell
$escapedTitle = $milestone.title -replace '([`*_{}[\]()#+\-.!])', '\$1'
```

**Effort**: 1 function, 3 call sites.

## Questions for Planner

1. **Convention dependency**: What happens if repository uses non-semantic milestones ("Q1 2026", "Sprint 15")? Should we support alternative versioning schemes via parameter?

2. **Workflow scope**: Should milestone tracking be limited to main branch merges? Current implementation tracks all branches (higher cost, potentially unnecessary).

3. **Delegation vs. inline**: Is the delegation to Set-IssueMilestone.ps1 worth the indirection? Skill adds 50 lines of code for validation that orchestrator already performs. Could we call `gh issue edit --milestone` directly?

4. **Failure recovery**: If milestone assignment fails (API error, permissions), should workflow retry or fail fast? No retry logic exists.

5. **Audit trail**: Should we log milestone changes to issue comments or project board for audit? Current implementation is silent.

## Recommendations

### Immediate Actions

1. **Add integration tests** for Set-IssueMilestone.ps1 delegation (Critical #1)
2. **Implement concurrency control** to prevent race conditions (Critical #3)
3. **Add -Force parameter** for override scenarios (Important #4)
4. **Move detection script** to `.claude/skills/github/scripts/milestone/` (Important #5)

### Follow-Up Actions

1. Document semantic milestone prerequisite in workflow README
2. Add -CreateIfMissing parameter for automatic milestone creation
3. Analyze workflow run costs and filter to main branch if warranted
4. Make version pattern configurable for pre-release support

### Optional Enhancements

1. Add rate limit pre-flight checks
2. Sanitize markdown in step summaries
3. Add audit trail comments to issues
4. Implement retry logic for transient API failures

## Approval Conditions

Before merging this implementation:

- [x] Integration tests for skill delegation added OR rationale for double-check pattern documented
- [x] Concurrency control added to workflow
- [x] -Force parameter implemented OR documented as future enhancement
- [x] Detection script location rationale documented (scripts/ vs skills/)
- [x] README added documenting semantic milestone prerequisite
- [x] Workflow run cost analysis completed OR filtering to main branch implemented

## Alternative Approaches

### Alternative 1: Use GitHub Projects API for Milestone Management

Instead of milestones, use GitHub Projects V2 with custom fields for version tracking. Benefits: more flexible, supports non-semantic versioning, integrates with project boards.

**Trade-off**: Higher complexity, requires project board setup, loses native milestone UI.

### Alternative 2: Hardcoded Milestone with Periodic Rotation

Follow moq.analyzers pattern with hardcoded "vNext" milestone, updated quarterly via scheduled workflow.

**Trade-off**: Simpler (no detection logic), less flexible (manual updates), documented maintenance burden.

### Alternative 3: Label-Based Version Tracking

Use labels instead of milestones ("version/0.2.0"), query via label API. Benefits: no milestone limit (GitHub limits milestones per repo), easier bulk updates.

**Trade-off**: Loses milestone progress tracking UI, requires label naming convention.

## Impact Analysis Review

Not applicable (no impact analysis performed for this implementation).

## Pre-PR Readiness Validation

### Validation Tasks Included

- [x] Plan includes cross-cutting concerns (exit codes, error handling, structured output)
- [x] Plan addresses fail-safe design (exit code standardization per ADR-035)
- [x] Plan includes test strategy (Pester tests for both scripts)
- [ ] Plan includes CI simulation testing (no evidence of manual workflow trigger testing)

### Gaps Identified

1. **CI simulation**: No evidence of manual workflow trigger testing before PR. Recommend adding workflow_dispatch trigger for testing.
2. **Environment variables**: No documentation of required environment variables (GH_TOKEN) in workflow README.
3. **Protected branch testing**: No evidence of testing on protected branch with required status checks.

### Pre-PR Readiness Verdict

**CONDITIONAL**: Approve with validation additions required.

Add workflow_dispatch trigger for manual testing:

```yaml
on:
  workflow_dispatch:
    inputs:
      item_type:
        description: 'Item type (pr or issue)'
        required: true
        type: choice
        options: [pr, issue]
      item_number:
        description: 'Item number'
        required: true
        type: number
  pull_request:
    types: [closed]
  issues:
    types: [closed]
```

## Verdict Rationale

Implementation demonstrates solid engineering discipline with ADR compliance, comprehensive testing structure, and DRY delegation. However, critical architectural risks (untested delegation, no semantic milestone fallback, race conditions) require resolution before production deployment. The semantic version auto-detection is powerful but introduces convention dependency that needs explicit handling.

**Confidence**: High (based on code review, test analysis, ADR compliance verification)

**Recommended Next Agent**: Planner (to address critical issues and questions)

## Appendix: Exit Code Reference

Per ADR-035, both scripts follow standardized exit codes:

| Code | Meaning | Scripts |
|------|---------|---------|
| 0 | Success | Both |
| 1 | Invalid parameters | Both |
| 2 | Milestone not found / No semantic milestones | Both |
| 3 | API error | Both |
| 4 | Not authenticated | GitHubCore.psm1 |
| 5 | Assignment failed (milestone exists without -Force) | Set-IssueMilestone.ps1 |

Exit code consistency enables predictable error handling in workflows.
