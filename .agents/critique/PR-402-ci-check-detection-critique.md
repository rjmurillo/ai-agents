# Plan Critique: CI Check Status Detection Implementation

**Date**: 2025-12-26
**PR**: #402 - fix(ci): add visibility message when PR maintenance processes 0 PRs
**Branch**: fix/400-pr-maintenance-visibility
**Reviewer**: critic agent

---

## Verdict

**APPROVED WITH CONDITIONS**

Implementation addresses root cause but has edge cases requiring attention before deployment.

---

## Summary

The CI check status detection implementation adds `statusCheckRollup` query to GraphQL and implements `Test-PRHasFailingChecks` to detect PRs with failing CI checks. This directly addresses the root cause: **PR #269 was missed because it had failing checks but reviewDecision was not CHANGES_REQUESTED**.

The implementation is technically sound but requires edge case handling and test coverage updates.

---

## Strengths

### 1. Root Cause Addressed

**Evidence**: PR #269 data shows:
- reviewDecision: APPROVED (final state after CHANGES_REQUESTED resolved)
- statusCheckRollup: Contains FAILURE checks ("Aggregate Results" check failed)
- Current script only triggered on CHANGES_REQUESTED, so PR was missed

**Fix**: Lines 665-678 now trigger ActionRequired when `$hasFailingChecks = $true`, regardless of reviewDecision.

### 2. Robust Property Accessor

The `Get-SafeProperty` helper (lines 427-449) correctly handles:
- Hashtables vs PSObjects (JSON parsing returns PSObjects)
- Strict mode compliance ($null checks)
- Array preservation (prevents PowerShell unrolling)

**Specific evidence of robustness**:
```powershell
# Line 445-447: Preserves arrays when returning
if ($null -ne $value -and $value -is [array]) {
    return @(,$value)  # Wrap in array to prevent unrolling
}
```

This is critical because GraphQL returns arrays for `nodes`, and PowerShell would otherwise unroll them.

### 3. Dual-Level Failure Detection

Lines 467-471: Checks overall state (FAILURE, ERROR)
Lines 473-491: Also checks individual check conclusions

This catches:
- Failed aggregate checks (overall state = FAILURE)
- Individual check failures (conclusion = FAILURE)
- StatusContext failures (state = FAILURE)

---

## Issues Found

### Critical (Must Fix)

**None** - Core logic is sound.

### Important (Should Fix)

#### Issue 1: Test Coverage Gap for `Test-PRHasFailingChecks`

**Location**: `tests/Invoke-PRMaintenance.Tests.ps1`

**Problem**: No test coverage for new function. Current tests mock at PR level but don't validate:
1. GraphQL structure navigation (nested nodes)
2. Array preservation in strict mode
3. Edge cases (null rollup, empty nodes, pending checks)

**Impact**: Moderate - function may fail on unexpected GraphQL responses

**Recommendation**:
```powershell
Describe 'Test-PRHasFailingChecks' {
    It 'Returns true when overall state is FAILURE' {
        $pr = @{
            commits = @{
                nodes = @(
                    @{
                        commit = @{
                            statusCheckRollup = @{
                                state = 'FAILURE'
                                contexts = @{ nodes = @() }
                            }
                        }
                    }
                )
            }
        }
        Test-PRHasFailingChecks -PR $pr | Should -Be $true
    }

    It 'Returns true when individual check has FAILURE conclusion' {
        $pr = @{
            commits = @{
                nodes = @(
                    @{
                        commit = @{
                            statusCheckRollup = @{
                                state = 'SUCCESS'
                                contexts = @{
                                    nodes = @(
                                        @{ conclusion = 'FAILURE'; name = 'Test Check' }
                                    )
                                }
                            }
                        }
                    }
                )
            }
        }
        Test-PRHasFailingChecks -PR $pr | Should -Be $true
    }

    It 'Returns false when no commits exist' {
        $pr = @{ commits = $null }
        Test-PRHasFailingChecks -PR $pr | Should -Be $false
    }

    It 'Returns false when statusCheckRollup is null' {
        $pr = @{
            commits = @{
                nodes = @(
                    @{ commit = @{ statusCheckRollup = $null } }
                )
            }
        }
        Test-PRHasFailingChecks -PR $pr | Should -Be $false
    }

    It 'Handles PSObject from JSON parsing (not hashtable)' {
        # Simulate ConvertFrom-Json output
        $json = @'
{
    "commits": {
        "nodes": [
            {
                "commit": {
                    "statusCheckRollup": {
                        "state": "FAILURE",
                        "contexts": { "nodes": [] }
                    }
                }
            }
        ]
    }
}
'@
        $pr = $json | ConvertFrom-Json
        Test-PRHasFailingChecks -PR $pr | Should -Be $true
    }
}
```

#### Issue 2: PENDING Checks Not Handled

**Location**: Lines 467-471

**Problem**: Only checks for FAILURE and ERROR states. Does not handle:
- PENDING checks (may indicate check never completed)
- EXPECTED state (GitHub's "expected" checks)

**Example**: PR #269 shows checks with `status: COMPLETED, conclusion: SUCCESS` but aggregate check has `conclusion: FAILURE`. Current logic would catch this, but a PR with all checks PENDING would be missed.

**Recommendation**:
```powershell
# Option A: Conservative - treat PENDING as failing for old PRs
if ($state -and $state -in @('FAILURE', 'ERROR', 'PENDING')) {
    # Check if PENDING for > 24 hours (stale check)
    $firstNode = $nodes[0]
    $commit = Get-SafeProperty $firstNode 'commit'
    $committedDate = Get-SafeProperty $commit 'committedDate'
    if ($state -eq 'PENDING' -and $committedDate) {
        $age = (Get-Date) - [DateTime]::Parse($committedDate)
        if ($age.TotalHours -gt 24) {
            return $true  # Stale pending check
        }
    }
    elseif ($state -in @('FAILURE', 'ERROR')) {
        return $true
    }
}

# Option B: Simple - only FAILURE/ERROR (current approach is acceptable)
# If checks are PENDING, PR likely shouldn't be merged anyway
```

**Decision**: Current approach (Option B) is acceptable. PENDING checks are not failures, they're in-progress. No change required, but document this behavior.

#### Issue 3: SKIPPED Checks May Hide Failures

**Location**: Lines 480-491

**Problem**: PR #269 shows:
```json
{"conclusion": "SKIPPED", "status": "COMPLETED", "name": "Run Pester Tests"}
```

SKIPPED checks are not failures, but if a REQUIRED check is SKIPPED, the PR shouldn't merge.

**Impact**: Low - GitHub branch protection handles required checks

**Recommendation**: Document that SKIPPED checks are ignored (expected behavior).

### Minor (Consider)

#### Issue 4: GraphQL Query Size May Hit Limits

**Location**: Lines 297-320

**Problem**: `contexts(first: 50)` retrieves up to 50 check contexts. Some PRs may have more.

**Evidence**: PR #269 has 31 checks. Likely won't exceed 50, but possible.

**Recommendation**: Add pagination or increase to 100:
```graphql
contexts(first: 100) {
    nodes {
        # ...
    }
}
```

#### Issue 5: Missing Documentation in Function Comment

**Location**: Lines 407-418

**Problem**: Doc comment doesn't mention:
- What return values mean (true = has failures, false = no failures or no checks)
- Edge cases (null rollup, no commits)
- PSObject vs hashtable handling

**Recommendation**:
```powershell
<#
.SYNOPSIS
    Checks if a PR has failing CI checks.

.DESCRIPTION
    Examines the statusCheckRollup from the PR's latest commit to determine
    if any required checks have failed. This enables detecting PRs that need
    attention due to CI failures (e.g., Session Protocol validation failures).

    Returns $true if:
    - Overall rollup state is FAILURE or ERROR
    - Any individual check has conclusion = FAILURE
    - Any StatusContext has state = FAILURE

    Returns $false if:
    - No commits exist
    - statusCheckRollup is null (no checks configured)
    - All checks passed or are pending

.PARAMETER PR
    The PR object from GraphQL query containing commits.nodes[0].commit.statusCheckRollup.
    Supports both hashtables and PSObjects (from ConvertFrom-Json).

.EXAMPLE
    $pr = Get-OpenPRs -Owner 'foo' -Repo 'bar' | Select-Object -First 1
    if (Test-PRHasFailingChecks -PR $pr) {
        Write-Host "PR has failing checks"
    }
#>
```

---

## Edge Cases Analysis

### Edge Case 1: PR with No Checks Configured

**Scenario**: Repository has no CI workflows

**Behavior**: statusCheckRollup is null, function returns $false

**Is this correct?** Yes - no checks = no failures

### Edge Case 2: All Checks SKIPPED

**Scenario**: PR changes paths that trigger no workflows (e.g., only changes .md files)

**Behavior**: All checks have conclusion = SKIPPED, function returns $false

**Is this correct?** Yes - SKIPPED != FAILURE

### Edge Case 3: Check Re-run In Progress

**Scenario**: PR had failing check, user re-ran it, now status = IN_PROGRESS

**Behavior**: Previous conclusion was FAILURE, current status is IN_PROGRESS

**Question**: Does GraphQL return the OLD conclusion or wait for new result?

**Evidence needed**: Test with re-run check to verify GraphQL behavior

**Mitigation**: Document that function reflects LATEST check state, not historical

### Edge Case 4: Multiple Commits in PR

**Scenario**: PR has 10 commits, only latest has statusCheckRollup

**Behavior**: Query uses `commits(last: 1)`, so only checks latest commit

**Is this correct?** Yes - GitHub runs checks on latest commit (HEAD)

---

## Integration with Classification Logic

### Trigger Conditions

**Agent-Controlled Bot** (lines 634-682):
- CHANGES_REQUESTED → ActionRequired ✓
- HAS_CONFLICTS → ActionRequired ✓
- **HAS_FAILING_CHECKS → ActionRequired** ✓ (NEW)

**Mention-Triggered Bot** (lines 683-708):
- CHANGES_REQUESTED → ActionRequired ✓
- HAS_CONFLICTS → ActionRequired ✓
- **HAS_FAILING_CHECKS → ActionRequired** ✓ (NEW)

**Human-Authored** (lines 709-733):
- CHANGES_REQUESTED → Blocked ✓
- HAS_CONFLICTS → Blocked ✓
- **HAS_FAILING_CHECKS → NOT HANDLED** ❌

### Issue 6: Human-Authored PRs with Failing Checks Not Classified

**Location**: Lines 709-733

**Problem**: Human PRs with failing checks are not added to Blocked or ActionRequired

**Example**:
```powershell
# Human PR with failing checks but no CHANGES_REQUESTED
$pr = @{
    author = @{ login = 'human' }
    reviewDecision = $null
    mergeable = 'MERGEABLE'
    hasFailingChecks = $true  # CI failing
}
# Result: No entry in Blocked or ActionRequired
```

**Impact**: Moderate - human PRs with CI failures are invisible to maintenance workflow

**Recommendation**:
```powershell
else {
    # Human-authored PRs or mention-triggered bots without rjmurillo-bot reviewer
    if ($hasChangesRequested) {
        # ... existing code ...
    }
    elseif ($hasConflicts) {
        # ... existing code ...
    }
    elseif ($hasFailingChecks) {
        # NEW: Human PR with failing checks
        Write-Log "PR #$($pr.number): Human-authored with failing checks" -Level INFO
        $null = $results.Blocked.Add(@{
            number = $pr.number
            category = 'human-blocked'
            hasConflicts = $false
            hasFailingChecks = $true
            reason = 'HAS_FAILING_CHECKS'
            author = $authorLogin
            title = $pr.title
        })
    }
}
```

---

## Questions for Planner

1. **PENDING checks**: Should stale PENDING checks (> 24 hours) be treated as failures?
2. **Human PR failing checks**: Should human-authored PRs with failing checks be added to Blocked?
3. **SKIPPED required checks**: Should we detect when a REQUIRED check is SKIPPED and flag it?
4. **GraphQL pagination**: Is 50 check contexts sufficient, or increase to 100?
5. **Test coverage**: Should we add unit tests for `Test-PRHasFailingChecks` before merge?

---

## Recommendations

### Must Complete Before Approval

1. **Add test coverage** for `Test-PRHasFailingChecks` (see Issue 1)
2. **Handle human PRs with failing checks** (see Issue 6)

### Should Complete for Production Readiness

3. **Document PENDING/SKIPPED behavior** in function doc comment
4. **Increase GraphQL context limit** to 100 (from 50)

### Consider for Future Enhancement

5. **Stale check detection**: Add logic to detect checks stuck in PENDING for > 24 hours
6. **Required check validation**: Verify REQUIRED checks are not SKIPPED

---

## Approval Conditions

- [ ] Add unit tests for `Test-PRHasFailingChecks` function
- [ ] Add classification for human PRs with failing checks (lines 709-733)
- [ ] Update function doc comment to document return values and edge cases
- [ ] Verify GraphQL context limit is sufficient (test with PR that has 50+ checks, or increase to 100)

Once these conditions are met, implementation is ready for deployment.

---

## Handoff Recommendation

**Status**: NEEDS REVISION

**Recommended next agent**: implementer

**Reason**: Implementation is 80% complete. Need to add:
1. Test coverage (15-20 lines)
2. Human PR classification (10 lines)
3. Doc comment update (5 lines)

Total additional work: ~30-35 lines

**Context for implementer**:
- Core logic is correct, no refactoring needed
- Add tests to `tests/Invoke-PRMaintenance.Tests.ps1` in existing `Describe 'Invoke-PRMaintenance Bot Authority Tests'` block
- Add human PR failing checks handling in else block at line 709
- Update doc comment at line 407

---

## Classification

**Completeness**: PARTIAL - Core feature complete, test coverage and edge case handling missing

**Feasibility**: HIGH - Changes are straightforward and low-risk

**Alignment**: CONFIRMED - Directly addresses root cause from PR #269 analysis

**Testability**: MODERATE - Needs test coverage for new function

**Reversibility**: HIGH - GraphQL query is additive, no breaking changes
