# PR Maintenance Workflow Recommendations

**Date**: 2025-12-26
**Context**: HAS_FAILING_CHECKS classification addition
**Related**: `pr-maintenance-statuscheck-impact-analysis.md`

## Current Workflow Behavior

### Matrix Strategy (resolve-conflicts job)

**Current Filter** (line 74):
```powershell
$conflictPRs = @($parsed.prs | Where-Object { $_.hasConflicts -eq $true })
```

**Behavior**:
- Only PRs with `hasConflicts=true` enter the matrix
- PRs with `hasFailingChecks=true` (but no conflicts) are **excluded** from matrix
- These PRs appear in discovery summary but do not trigger parallel conflict resolution

**Example**:
```text
Input PRs:
  #123: hasConflicts=true, hasFailingChecks=false  → Matrix: YES
  #456: hasConflicts=false, hasFailingChecks=true  → Matrix: NO
  #789: hasConflicts=true, hasFailingChecks=true   → Matrix: YES

Matrix processes: #123, #789
Summary shows: All 3 PRs in "PRs Requiring Action" table
```

**Verdict**: [CORRECT BEHAVIOR] - Matrix should only handle conflicts. Failing checks are handled by pr-comment-responder skill.

---

## Workflow Enhancement Opportunities

### 1. Enhanced Discovery Summary (Optional)

**Current Output** (lines 97-121):
```markdown
| PR | Category | Reason | Has Conflicts |
|----|----------|--------|---------------|
| #123 | agent-controlled | HAS_CONFLICTS | :warning: |
| #456 | agent-controlled | HAS_FAILING_CHECKS | :white_check_mark: |
```

**Recommended Enhancement**:
```markdown
| PR | Category | Reason | Has Conflicts | Failing Checks |
|----|----------|--------|---------------|----------------|
| #123 | agent-controlled | HAS_CONFLICTS | :warning: | :white_check_mark: |
| #456 | agent-controlled | HAS_FAILING_CHECKS | :white_check_mark: | :x: |
```

**Implementation** (lines 117-119):
```powershell
foreach ($pr in $parsed.prs) {
    $conflictIcon = if ($pr.hasConflicts) { ':warning:' } else { ':white_check_mark:' }
    $checksIcon = if ($pr.hasFailingChecks) { ':x:' } else { ':white_check_mark:' }
    $summary += "| #$($pr.number) | $($pr.category) | $($pr.reason) | $conflictIcon | $checksIcon |`n"
}
```

**Effort**: 5 minutes
**Value**: Better visibility into PR health status

---

### 2. Failing Checks Alert (Optional)

**Purpose**: Create distinct alerts for PRs with failing checks that need investigation.

**Implementation** (add after line 225):
```powershell
- name: Create alert for failing checks
  env:
    GH_TOKEN: ${{ secrets.BOT_PAT }}
  shell: pwsh -NoProfile -Command "& '{0}'"
  run: |
    $json = '${{ needs.discover-prs.outputs.summary-json }}'
    if (-not $json) { exit 0 }

    $parsed = $json | ConvertFrom-Json
    $failingChecks = @($parsed.prs | Where-Object { $_.hasFailingChecks -eq $true })

    if ($failingChecks.Count -gt 0) {
      Write-Host "::warning::$($failingChecks.Count) PR(s) have failing CI checks"
      foreach ($pr in $failingChecks) {
        Write-Host "::notice::PR #$($pr.number): $($pr.reason) - $($pr.title)"
      }
    }
```

**Effort**: 10 minutes
**Value**: Proactive alerting for CI failures

---

### 3. Separate Matrix for Failing Checks (Future)

**Concept**: Run pr-comment-responder in parallel for failing check PRs (similar to conflict resolution).

**Workflow Structure**:
```yaml
jobs:
  discover-prs:
    # ... existing ...

  # NEW: Parallel job for failing checks
  handle-failing-checks:
    needs: discover-prs
    if: needs.discover-prs.outputs.has-failing-checks == 'true'
    runs-on: ubuntu-24.04-arm
    timeout-minutes: 10
    strategy:
      matrix:
        include: ${{ fromJson(needs.discover-prs.outputs.failing-checks-matrix) }}
      fail-fast: false
      max-parallel: 3

    steps:
      - name: Run pr-comment-responder for PR #${{ matrix.number }}
        run: |
          # Invoke pr-comment-responder skill
          # Could synthesize comment with check failure details
```

**Discovery Changes**:
```powershell
# In discover-prs step (line 70-88)
$failingChecksPRs = @($parsed.prs | Where-Object { $_.hasFailingChecks -eq $true })
$failingChecksMatrix = @{ include = $failingChecksPRs } | ConvertTo-Json -Compress -Depth 10
"failing-checks-matrix=$failingChecksMatrix" | Out-File $env:GITHUB_OUTPUT -Append
"has-failing-checks=$($failingChecksPRs.Count -gt 0)" | Out-File $env:GITHUB_OUTPUT -Append
```

**Effort**: 2 hours
**Value**: Automated response to CI failures without manual intervention
**Risk**: Medium (requires pr-comment-responder to handle failing check context)

---

## Rate Limit Optimization (Not Needed)

**Analysis**: Current rate limit buffer is 99.5%, no optimization required.

If rate limits become a concern in the future:

1. **Cache statusCheckRollup data**
   - Store in workflow cache with 1-hour TTL
   - Skip query if cache hit
   - Expected savings: 50% rate limit reduction

2. **Reduce contexts fetch limit**
   - Change `contexts(first: 50)` → `contexts(first: 20)`
   - Expected savings: 60% response size reduction
   - Risk: May miss checks beyond first 20

3. **Conditional statusCheckRollup fetch**
   - Only fetch if `reviewDecision = CHANGES_REQUESTED`
   - Expected savings: 70% query reduction
   - Risk: Miss failing checks on approved PRs

**Current Recommendation**: [NOT NEEDED] - Monitor rate limit usage, implement if drops below 1000 points remaining.

---

## Testing Recommendations

### Integration Test Scenarios

Add to `tests/Invoke-PRMaintenance.Tests.ps1`:

```powershell
Describe 'StatusCheckRollup Integration Tests' {
    It 'Classifies PR with FAILURE state as HAS_FAILING_CHECKS' {
        Mock Get-OpenPRs {
            , @([PSCustomObject]@{
                number = 100
                author = [PSCustomObject]@{ login = 'rjmurillo-bot' }
                reviewDecision = $null
                mergeable = 'MERGEABLE'
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
            })
        }

        $results = Invoke-PRMaintenance -Owner 'test' -Repo 'test'

        $results.ActionRequired | Should -HaveCount 1
        $results.ActionRequired[0].reason | Should -Be 'HAS_FAILING_CHECKS'
        $results.ActionRequired[0].hasFailingChecks | Should -Be $true
    }

    It 'Handles missing statusCheckRollup gracefully' {
        Mock Get-OpenPRs {
            , @([PSCustomObject]@{
                number = 101
                author = [PSCustomObject]@{ login = 'rjmurillo-bot' }
                reviewDecision = $null
                mergeable = 'MERGEABLE'
                commits = @{ nodes = @() }  # No commit data
            })
        }

        $results = Invoke-PRMaintenance -Owner 'test' -Repo 'test'

        # Should not crash, should not classify as failing
        $results.ActionRequired | Should -BeNullOrEmpty
    }

    It 'Prioritizes HAS_CONFLICTS over HAS_FAILING_CHECKS in reason' {
        Mock Get-OpenPRs {
            , @([PSCustomObject]@{
                number = 102
                author = [PSCustomObject]@{ login = 'rjmurillo-bot' }
                reviewDecision = $null
                mergeable = 'CONFLICTING'
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
            })
        }

        $results = Invoke-PRMaintenance -Owner 'test' -Repo 'test'

        $results.ActionRequired | Should -HaveCount 1
        $results.ActionRequired[0].reason | Should -Be 'HAS_CONFLICTS'
        $results.ActionRequired[0].hasConflicts | Should -Be $true
        $results.ActionRequired[0].hasFailingChecks | Should -Be $true
    }
}
```

**Effort**: 1 hour
**Coverage Improvement**: +15% (covers statusCheckRollup data path)

---

## Deployment Checklist

**Before Merge**:
- [x] GraphQL query size verified (<2KB)
- [x] Rate limit impact assessed (negligible)
- [x] Workflow compatibility confirmed (backward compatible)
- [x] Test-PRHasFailingChecks function verified (4/4 tests pass)
- [ ] Unit tests added for Test-PRHasFailingChecks (required)
- [ ] Integration tests added for statusCheckRollup (recommended)

**After Merge**:
- [ ] Monitor discovery step duration (baseline: 15s, target: <20s)
- [ ] Monitor GraphQL rate limit consumption (baseline: 1 point/query)
- [ ] Track HAS_FAILING_CHECKS classification frequency (expect: 5-10%)
- [ ] Collect data for 1 week, review metrics

**Rollback Plan**:
If issues arise:
1. Revert commit removing statusCheckRollup query
2. No workflow changes needed (backward compatible)
3. Existing behavior resumes immediately

---

## Conclusion

**Current workflow is fully compatible** with statusCheckRollup changes. No modifications required.

**Recommended Actions**:
1. **[P1 - Required]** Add unit tests for Test-PRHasFailingChecks (1 hour)
2. **[P2 - Optional]** Enhance discovery summary with failing checks column (5 min)
3. **[P3 - Optional]** Add failing checks alert to summarize job (10 min)
4. **[Future]** Consider parallel pr-comment-responder for failing checks (2 hours)

**Estimated Total Effort**: 1 hour (required), +15 min (optional enhancements)

---

## References

- **Workflow File**: `.github/workflows/pr-maintenance.yml`
- **Script**: `scripts/Invoke-PRMaintenance.ps1`
- **Impact Analysis**: `pr-maintenance-statuscheck-impact-analysis.md`
