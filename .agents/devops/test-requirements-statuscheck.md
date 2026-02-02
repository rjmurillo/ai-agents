# Test Requirements: StatusCheck Enhancement

**Date**: 2025-12-26
**Component**: `scripts/Invoke-PRMaintenance.ps1`
**Test File**: `tests/Invoke-PRMaintenance.Tests.ps1`
**Priority**: P1 (Required before merge)

## Test Coverage Analysis

### Current Coverage

| Component | Test Count | Status |
|-----------|-----------|--------|
| Bot Authority | 6 tests | ✅ Complete |
| Conflict Detection | 4 tests | ✅ Complete |
| Derivative PRs | 2 tests | ✅ Complete |
| **StatusCheck Detection** | **0 tests** | ❌ **Missing** |

### Coverage Gap

**Function**: `Test-PRHasFailingChecks` (lines 406-493)
**Complexity**: Medium (nested null-safe navigation)
**Current Coverage**: 0%
**Target Coverage**: 100% (5 test cases)

---

## Required Test Cases

### Test Suite: StatusCheckRollup Detection

**Location**: Add to `tests/Invoke-PRMaintenance.Tests.ps1` after existing test suite.

```powershell
Describe 'Test-PRHasFailingChecks Function Tests' {
    BeforeAll {
        . "$PSScriptRoot/../scripts/Invoke-PRMaintenance.ps1"
    }

    Context 'Rollup State Detection' {
        It 'Returns true when statusCheckRollup.state is FAILURE' {
            # Arrange
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

            # Act
            $result = Test-PRHasFailingChecks -PR $pr

            # Assert
            $result | Should -Be $true
        }

        It 'Returns true when statusCheckRollup.state is ERROR' {
            # Arrange
            $pr = @{
                commits = @{
                    nodes = @(
                        @{
                            commit = @{
                                statusCheckRollup = @{
                                    state = 'ERROR'
                                    contexts = @{ nodes = @() }
                                }
                            }
                        }
                    )
                }
            }

            # Act
            $result = Test-PRHasFailingChecks -PR $pr

            # Assert
            $result | Should -Be $true
        }

        It 'Returns false when statusCheckRollup.state is SUCCESS' {
            # Arrange
            $pr = @{
                commits = @{
                    nodes = @(
                        @{
                            commit = @{
                                statusCheckRollup = @{
                                    state = 'SUCCESS'
                                    contexts = @{ nodes = @() }
                                }
                            }
                        }
                    )
                }
            }

            # Act
            $result = Test-PRHasFailingChecks -PR $pr

            # Assert
            $result | Should -Be $false
        }

        It 'Returns false when statusCheckRollup.state is PENDING' {
            # Arrange
            $pr = @{
                commits = @{
                    nodes = @(
                        @{
                            commit = @{
                                statusCheckRollup = @{
                                    state = 'PENDING'
                                    contexts = @{ nodes = @() }
                                }
                            }
                        }
                    )
                }
            }

            # Act
            $result = Test-PRHasFailingChecks -PR $pr

            # Assert
            $result | Should -Be $false
        }
    }

    Context 'Individual Check Detection' {
        It 'Returns true when a CheckRun has FAILURE conclusion' {
            # Arrange
            $pr = @{
                commits = @{
                    nodes = @(
                        @{
                            commit = @{
                                statusCheckRollup = @{
                                    state = 'PENDING'
                                    contexts = @{
                                        nodes = @(
                                            @{ name = 'passing-test'; conclusion = 'SUCCESS'; status = 'COMPLETED' }
                                            @{ name = 'failing-test'; conclusion = 'FAILURE'; status = 'COMPLETED' }
                                        )
                                    }
                                }
                            }
                        }
                    )
                }
            }

            # Act
            $result = Test-PRHasFailingChecks -PR $pr

            # Assert
            $result | Should -Be $true
        }

        It 'Returns true when a StatusContext has FAILURE state' {
            # Arrange
            $pr = @{
                commits = @{
                    nodes = @(
                        @{
                            commit = @{
                                statusCheckRollup = @{
                                    state = 'PENDING'
                                    contexts = @{
                                        nodes = @(
                                            @{ context = 'ci/test'; state = 'FAILURE' }
                                        )
                                    }
                                }
                            }
                        }
                    )
                }
            }

            # Act
            $result = Test-PRHasFailingChecks -PR $pr

            # Assert
            $result | Should -Be $true
        }

        It 'Returns false when all checks are passing' {
            # Arrange
            $pr = @{
                commits = @{
                    nodes = @(
                        @{
                            commit = @{
                                statusCheckRollup = @{
                                    state = 'SUCCESS'
                                    contexts = @{
                                        nodes = @(
                                            @{ name = 'test-1'; conclusion = 'SUCCESS'; status = 'COMPLETED' }
                                            @{ name = 'test-2'; conclusion = 'SUCCESS'; status = 'COMPLETED' }
                                            @{ context = 'ci/test'; state = 'SUCCESS' }
                                        )
                                    }
                                }
                            }
                        }
                    )
                }
            }

            # Act
            $result = Test-PRHasFailingChecks -PR $pr

            # Assert
            $result | Should -Be $false
        }
    }

    Context 'Null Safety and Edge Cases' {
        It 'Returns false when commits.nodes is empty' {
            # Arrange
            $pr = @{
                commits = @{ nodes = @() }
            }

            # Act
            $result = Test-PRHasFailingChecks -PR $pr

            # Assert
            $result | Should -Be $false
        }

        It 'Returns false when commits is null' {
            # Arrange
            $pr = @{
                commits = $null
            }

            # Act
            $result = Test-PRHasFailingChecks -PR $pr

            # Assert
            $result | Should -Be $false
        }

        It 'Returns false when statusCheckRollup is missing' {
            # Arrange
            $pr = @{
                commits = @{
                    nodes = @(
                        @{
                            commit = @{}  # No statusCheckRollup
                        }
                    )
                }
            }

            # Act
            $result = Test-PRHasFailingChecks -PR $pr

            # Assert
            $result | Should -Be $false
        }

        It 'Returns false when contexts.nodes is null' {
            # Arrange
            $pr = @{
                commits = @{
                    nodes = @(
                        @{
                            commit = @{
                                statusCheckRollup = @{
                                    state = 'PENDING'
                                    contexts = @{ nodes = $null }
                                }
                            }
                        }
                    )
                }
            }

            # Act
            $result = Test-PRHasFailingChecks -PR $pr

            # Assert
            $result | Should -Be $false
        }

        It 'Returns false when PR is null' {
            # Arrange
            $pr = $null

            # Act
            $result = Test-PRHasFailingChecks -PR $pr

            # Assert
            $result | Should -Be $false
        }
    }

    Context 'PSObject Compatibility (from JSON)' {
        It 'Handles PSObject from ConvertFrom-Json correctly' {
            # Arrange - Simulate GitHub API response
            $json = @'
{
  "commits": {
    "nodes": [
      {
        "commit": {
          "statusCheckRollup": {
            "state": "FAILURE",
            "contexts": {
              "nodes": [
                {"name": "ci-test", "conclusion": "FAILURE", "status": "COMPLETED"}
              ]
            }
          }
        }
      }
    ]
  }
}
'@
            $pr = $json | ConvertFrom-Json

            # Act
            $result = Test-PRHasFailingChecks -PR $pr

            # Assert
            $result | Should -Be $true
        }
    }
}
```

---

## Integration Test Cases

**Location**: Add to `tests/Invoke-PRMaintenance.Tests.ps1` in existing `Describe 'Invoke-PRMaintenance Bot Authority Tests'` block.

```powershell
# Add after line 227 (after last test case)

It 'Classifies PR with failing checks as HAS_FAILING_CHECKS' {
    # Arrange
    Mock Get-BotAuthorInfo { @{ IsBot = $true; Category = 'agent-controlled'; Action = 'pr-comment-responder'; Mention = $null } }
    Mock Get-OpenPRs {
        , @([PSCustomObject]@{
            number = 500
            title = 'PR with failing checks'
            author = [PSCustomObject]@{ login = 'rjmurillo-bot' }
            reviewDecision = $null
            mergeable = 'MERGEABLE'
            headRefName = 'feature'
            baseRefName = 'main'
            reviewRequests = @()
            commits = @{
                nodes = @(
                    @{
                        commit = @{
                            statusCheckRollup = @{
                                state = 'FAILURE'
                                contexts = @{
                                    nodes = @(
                                        @{ name = 'ci-test'; conclusion = 'FAILURE'; status = 'COMPLETED' }
                                    )
                                }
                            }
                        }
                    }
                )
            }
        })
    }
    Mock Get-PRComments { , @() }
    Mock Get-UnacknowledgedComments { , @() }

    # Act
    $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

    # Assert
    $results.ActionRequired | Should -HaveCount 1
    $results.ActionRequired[0].reason | Should -Be 'HAS_FAILING_CHECKS'
    $results.ActionRequired[0].hasFailingChecks | Should -Be $true
    $results.ActionRequired[0].hasConflicts | Should -Be $false
}

It 'Prioritizes HAS_CONFLICTS over HAS_FAILING_CHECKS when both present' {
    # Arrange
    Mock Get-BotAuthorInfo { @{ IsBot = $true; Category = 'agent-controlled'; Action = 'pr-comment-responder'; Mention = $null } }
    Mock Get-OpenPRs {
        , @([PSCustomObject]@{
            number = 501
            title = 'PR with conflicts and failing checks'
            author = [PSCustomObject]@{ login = 'rjmurillo-bot' }
            reviewDecision = $null
            mergeable = 'CONFLICTING'  # Has conflicts
            headRefName = 'feature'
            baseRefName = 'main'
            reviewRequests = @()
            commits = @{
                nodes = @(
                    @{
                        commit = @{
                            statusCheckRollup = @{
                                state = 'FAILURE'  # Also has failing checks
                                contexts = @{ nodes = @() }
                            }
                        }
                    }
                )
            }
        })
    }
    Mock Get-PRComments { , @() }
    Mock Get-UnacknowledgedComments { , @() }

    # Act
    $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

    # Assert
    $results.ActionRequired | Should -HaveCount 1
    $results.ActionRequired[0].reason | Should -Be 'HAS_CONFLICTS'  # Conflicts take priority
    $results.ActionRequired[0].hasConflicts | Should -Be $true
    $results.ActionRequired[0].hasFailingChecks | Should -Be $true  # But flag is set
}

It 'Does not trigger action for PR with passing checks' {
    # Arrange
    Mock Get-BotAuthorInfo { @{ IsBot = $true; Category = 'agent-controlled'; Action = 'pr-comment-responder'; Mention = $null } }
    Mock Get-OpenPRs {
        , @([PSCustomObject]@{
            number = 502
            title = 'PR with passing checks'
            author = [PSCustomObject]@{ login = 'rjmurillo-bot' }
            reviewDecision = $null
            mergeable = 'MERGEABLE'
            headRefName = 'feature'
            baseRefName = 'main'
            reviewRequests = @()
            commits = @{
                nodes = @(
                    @{
                        commit = @{
                            statusCheckRollup = @{
                                state = 'SUCCESS'
                                contexts = @{
                                    nodes = @(
                                        @{ name = 'ci-test'; conclusion = 'SUCCESS'; status = 'COMPLETED' }
                                    )
                                }
                            }
                        }
                    }
                )
            }
        })
    }
    Mock Get-PRComments { , @() }
    Mock Get-UnacknowledgedComments { , @() }

    # Act
    $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

    # Assert
    $results.ActionRequired | Should -BeNullOrEmpty
}
```

---

## Test Execution Plan

### Step 1: Run Unit Tests

```bash
pwsh -Command "Invoke-Pester -Path ./tests/Invoke-PRMaintenance.Tests.ps1 -Output Detailed"
```

**Expected Results**:
- All 6 existing tests: [PASS]
- 13 new statusCheck tests: [PASS]
- 3 new integration tests: [PASS]
- Total: 22 tests

### Step 2: Run Integration Tests

```bash
pwsh -Command "Invoke-Pester -Path ./tests/Integration-PRMaintenance.Tests.ps1 -Output Detailed"
```

**Expected Results**:
- Existing integration tests: [PASS]
- No new failures introduced

### Step 3: Coverage Report

```bash
pwsh -Command "
Invoke-Pester -Path ./tests/Invoke-PRMaintenance.Tests.ps1 `
  -CodeCoverage ./scripts/Invoke-PRMaintenance.ps1 `
  -CodeCoverageOutputFile ./coverage.xml
"
```

**Target Coverage**:
- Overall: >80%
- Test-PRHasFailingChecks: 100%
- Classification logic: >90%

---

## Test Implementation Effort

| Task | Effort | Priority |
|------|--------|----------|
| Add unit tests for Test-PRHasFailingChecks | 45 min | P1 |
| Add integration tests for HAS_FAILING_CHECKS | 15 min | P1 |
| Run tests and verify coverage | 10 min | P1 |
| Fix any failing tests | 20 min | P1 |
| **Total** | **90 min** | **P1** |

---

## Success Criteria

**Definition of Done**:
- [ ] All 13 unit tests for Test-PRHasFailingChecks pass
- [ ] All 3 integration tests for HAS_FAILING_CHECKS pass
- [ ] No regressions in existing tests (6/6 pass)
- [ ] Code coverage for Test-PRHasFailingChecks: 100%
- [ ] All tests use strict mode (`Set-StrictMode -Version Latest`)
- [ ] All tests validate null safety and edge cases

**Quality Gates**:
- Pester exit code: 0 (all tests pass)
- PSScriptAnalyzer: No errors
- Test execution time: <30 seconds

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Get-SafeProperty doesn't handle PSObject | LOW | HIGH | Test with ConvertFrom-Json output |
| Nested null checks fail in strict mode | LOW | MEDIUM | Test all null cases explicitly |
| Mock data doesn't match real API response | MEDIUM | LOW | Use actual GraphQL response structure |

---

## References

- **Function Under Test**: `scripts/Invoke-PRMaintenance.ps1` (lines 406-493)
- **Existing Tests**: `tests/Invoke-PRMaintenance.Tests.ps1`
- **Integration Tests**: `tests/Integration-PRMaintenance.Tests.ps1`
- **Impact Analysis**: `pr-maintenance-statuscheck-impact-analysis.md`
- **Workflow Recommendations**: `pr-maintenance-workflow-recommendations.md`
