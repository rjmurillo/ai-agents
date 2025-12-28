# Test Gap Analysis: PR #402

**Date**: 2025-12-26
**Feature**: PR Maintenance Workflow Enhancement
**Analysis Type**: Test Coverage and Quality Assessment

## Executive Summary

**Overall Assessment**: Implementation appears sound based on unit tests, but has 3 critical test gaps and 1 blocking bug:

- **P0 Blockers**: Integration test bug, multi-PR deduplication, conflict+CHANGES interaction
- **P1 Gaps**: Bot categories (3 of 6), synthesis edge cases, mock verification
- **P2 Gaps**: Derivative PR workflow (~200 LOC untested), error resilience

**Recommendation**: Address P0 issues before merge. P1/P2 can follow in separate PRs.

---

## P0 Gaps - Critical

### 1. Integration Test Bug (BLOCKER)

**Location**: `tests/Integration-PRMaintenance.Tests.ps1:14-15`

**Current Code**:
```powershell
$openPRs = gh pr list --repo "$Owner/$Repo" --state open --json number 2>$null | ConvertFrom-Json
$script:OpenPRNumbers = @($openPRs.number)  # BUG: PropertyNotFoundException
```

**Problem**: `$openPRs` is an array of objects like `[{number: 441}, {number: 438}]`. Accessing `.number` on the array fails.

**Fix**:
```powershell
$openPRs = gh pr list --repo "$Owner/$Repo" --state open --json number 2>$null | ConvertFrom-Json
$script:OpenPRNumbers = @($openPRs | ForEach-Object { $_.number })
```

**Impact**: Integration tests cannot run, preventing real-world validation of the implementation.

**Verification**: After fix, run:
```powershell
Invoke-Pester -Path tests/Integration-PRMaintenance.Tests.ps1 -Output Detailed
```

---

### 2. Multi-PR Deduplication Not Tested

**Current Test Coverage**: Test 4 validates single PR does not appear in both ActionRequired and Blocked.

**Missing Scenario**: Multiple PRs with the same condition.

**Proposed Test**:
```powershell
It 'Multiple bot PRs with conflicts and CHANGES_REQUESTED have no duplicates' {
    # Arrange - 3 bot PRs, all with conflicts + CHANGES_REQUESTED
    Mock Get-BotAuthorInfo { @{ IsBot = $true; Category = 'agent-controlled'; Action = 'pr-comment-responder'; Mention = $null } }
    Mock Resolve-PRConflicts { return $false }  # All fail conflict resolution
    Mock Get-OpenPRs {
        , @(
            [PSCustomObject]@{
                number = 101
                title = 'Bot PR 1'
                author = [PSCustomObject]@{ login = 'rjmurillo-bot' }
                reviewDecision = 'CHANGES_REQUESTED'
                mergeable = 'CONFLICTING'
                headRefName = 'feature-1'
                baseRefName = 'main'
                reviewRequests = @()
            }
            [PSCustomObject]@{
                number = 102
                title = 'Bot PR 2'
                author = [PSCustomObject]@{ login = 'rjmurillo-bot' }
                reviewDecision = 'CHANGES_REQUESTED'
                mergeable = 'CONFLICTING'
                headRefName = 'feature-2'
                baseRefName = 'main'
                reviewRequests = @()
            }
            [PSCustomObject]@{
                number = 103
                title = 'Bot PR 3'
                author = [PSCustomObject]@{ login = 'rjmurillo-bot' }
                reviewDecision = 'CHANGES_REQUESTED'
                mergeable = 'CONFLICTING'
                headRefName = 'feature-3'
                baseRefName = 'main'
                reviewRequests = @()
            }
        )
    }
    Mock Get-PRComments { , @() }
    Mock Get-UnacknowledgedComments { , @() }

    # Act
    $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

    # Assert - Each PR appears exactly once in ActionRequired
    $results.ActionRequired | Should -HaveCount 3

    # Assert - Each specific PR appears exactly once
    $pr101Entries = @($results.ActionRequired | Where-Object { $_.PR -eq 101 })
    $pr102Entries = @($results.ActionRequired | Where-Object { $_.PR -eq 102 })
    $pr103Entries = @($results.ActionRequired | Where-Object { $_.PR -eq 103 })

    $pr101Entries | Should -HaveCount 1
    $pr102Entries | Should -HaveCount 1
    $pr103Entries | Should -HaveCount 1

    # Assert - None in Blocked
    $results.Blocked | Should -HaveCount 0
}
```

**Why Important**: Current test validates single PR. Production could have multiple PRs with duplicate entries if deduplication logic fails at scale.

---

### 3. Conflict + CHANGES_REQUESTED Interaction

**Current Test Coverage**: Separate tests for conflicts and CHANGES_REQUESTED, but not both simultaneously.

**Missing Scenario**: Bot PR has BOTH unresolvable conflicts AND CHANGES_REQUESTED.

**Expected Behavior** (from code line 1506-1512):
```powershell
# If PR already in ActionRequired, merge conflict info
if ($alreadyInActionRequired) {
    $alreadyInActionRequired.HasConflicts = $true
    $alreadyInActionRequired.Action = "$($alreadyInActionRequired.Action) + resolve conflicts"
}
```

**Proposed Test**:
```powershell
It 'Bot PR with conflicts and CHANGES_REQUESTED merges action text' {
    # Arrange - Bot PR with BOTH conditions
    Mock Get-BotAuthorInfo { @{ IsBot = $true; Category = 'agent-controlled'; Action = 'pr-comment-responder'; Mention = $null } }
    Mock Resolve-PRConflicts { return $false }  # Conflict resolution fails
    Mock Get-OpenPRs {
        , @([PSCustomObject]@{
            number = 250
            title = 'Bot PR with both conflicts and changes requested'
            author = [PSCustomObject]@{ login = 'rjmurillo-bot' }
            reviewDecision = 'CHANGES_REQUESTED'
            mergeable = 'CONFLICTING'
            headRefName = 'feature-branch'
            baseRefName = 'main'
            reviewRequests = @()
        })
    }
    Mock Get-PRComments { , @() }
    Mock Get-UnacknowledgedComments {
        , @(
            [PSCustomObject]@{ id = 1; body = 'Fix this'; user = [PSCustomObject]@{ login = 'coderabbitai' } }
        )
    }

    # Act
    $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

    # Assert - Single entry in ActionRequired
    $prEntries = @($results.ActionRequired | Where-Object { $_.PR -eq 250 })
    $prEntries | Should -HaveCount 1

    # Assert - Action text contains both concerns
    $prEntries[0].Action | Should -Match 'resolve conflicts'

    # Assert - HasConflicts property set
    $prEntries[0].HasConflicts | Should -Be $true

    # Assert - Not in Blocked
    $results.Blocked | Where-Object { $_.PR -eq 250 } | Should -BeNullOrEmpty
}
```

**Why Important**: Code has explicit logic to merge action text (line 1511), but this path is untested. Could regress.

---

## P1 Gaps - Important

### 4. Bot Category Coverage

**Current Coverage**: Tests for `agent-controlled` and `mention-triggered` (2 of 6 categories).

**Missing Categories**:
1. `unknown-bot` - Bot with [bot] suffix but not recognized
2. `non-responsive` - github-actions[bot], cannot respond to comments
3. `command-triggered` - dependabot[bot], responds to commands

**Proposed Tests**:

```powershell
It 'Unknown bot category triggers manual review' {
    # Arrange - Unrecognized bot
    Mock Get-BotAuthorInfo { @{ IsBot = $true; Category = 'unknown-bot'; Action = 'Review manually - unknown bot type'; Mention = $null } }
    Mock Resolve-PRConflicts { return $true }
    Mock Get-OpenPRs {
        , @([PSCustomObject]@{
            number = 300
            title = 'PR from unknown bot'
            author = [PSCustomObject]@{ login = 'foobar[bot]' }
            reviewDecision = 'CHANGES_REQUESTED'
            mergeable = 'MERGEABLE'
            headRefName = 'feature'
            baseRefName = 'main'
            reviewRequests = @()
        })
    }
    Mock Get-PRComments { , @() }

    # Act
    $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

    # Assert - In ActionRequired with manual review action
    $results.ActionRequired | Should -HaveCount 1
    $results.ActionRequired[0].Category | Should -Be 'unknown-bot'
    $results.ActionRequired[0].Action | Should -Match 'Review manually'
}

It 'Non-responsive bot goes to Blocked with migration recommendation' {
    # Arrange - github-actions[bot]
    Mock Get-BotAuthorInfo { @{ IsBot = $true; Category = 'non-responsive'; Action = 'Blocked - bot cannot respond to comments. Recommend migrating to user-specific credentials.'; Mention = $null } }
    Mock Resolve-PRConflicts { return $true }
    Mock Get-OpenPRs {
        , @([PSCustomObject]@{
            number = 400
            title = 'PR from github-actions'
            author = [PSCustomObject]@{ login = 'github-actions[bot]' }
            reviewDecision = 'CHANGES_REQUESTED'
            mergeable = 'MERGEABLE'
            headRefName = 'feature'
            baseRefName = 'main'
            reviewRequests = @()
        })
    }
    Mock Get-PRComments { , @() }

    # Act
    $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

    # Assert - Appropriate handling of non-responsive bot
    # (Implementation may vary - this is the expected behavior per cursor[bot] review)
    $results.Blocked | Should -HaveCount 1
    $results.Blocked[0].Action | Should -Match 'migrate'
}

It 'Command-triggered bot suggests appropriate commands' {
    # Arrange - dependabot[bot]
    Mock Get-BotAuthorInfo { @{ IsBot = $true; Category = 'command-triggered'; Action = 'Use @dependabot commands (e.g., rebase, recreate)'; Mention = '@dependabot' } }
    Mock Resolve-PRConflicts { return $true }
    Mock Get-OpenPRs {
        , @([PSCustomObject]@{
            number = 500
            title = 'Dependency update'
            author = [PSCustomObject]@{ login = 'dependabot[bot]' }
            reviewDecision = 'CHANGES_REQUESTED'
            mergeable = 'MERGEABLE'
            headRefName = 'dependabot/npm'
            baseRefName = 'main'
            reviewRequests = @()
        })
    }
    Mock Get-PRComments { , @() }

    # Act
    $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

    # Assert - In ActionRequired with command suggestion
    $results.ActionRequired | Should -HaveCount 1
    $results.ActionRequired[0].Category | Should -Be 'command-triggered'
    $results.ActionRequired[0].Action | Should -Match '@dependabot'
}
```

**Why Important**: Get-BotAuthorInfo has 6 categories (lines 655-803), but only 2 are tested. Unknown behavior for production scenarios.

---

### 5. Synthesis Edge Cases

**Current Coverage**: Happy path only (3 comments from 2 bots).

**Missing Scenarios**:

```powershell
It 'Copilot synthesis with large number of comments does not fail' {
    # Arrange - 100 bot comments
    Mock Get-BotAuthorInfo -ParameterFilter { $AuthorLogin -imatch 'copilot' } {
        @{ IsBot = $true; Category = 'mention-triggered'; Action = 'mention in comment'; Mention = '@copilot' }
    }
    Mock Resolve-PRConflicts { return $true }
    Mock Get-OpenPRs {
        , @([PSCustomObject]@{
            number = 600
            title = 'Copilot PR with many comments'
            author = [PSCustomObject]@{ login = 'copilot-swe-agent' }
            reviewDecision = 'CHANGES_REQUESTED'
            mergeable = 'MERGEABLE'
            headRefName = 'feature'
            baseRefName = 'main'
            reviewRequests = @([PSCustomObject]@{ login = 'rjmurillo-bot' })
        })
    }

    # Generate 100 bot comments
    $manyComments = 1..100 | ForEach-Object {
        [PSCustomObject]@{
            id = $_
            body = "Comment $_"
            user = [PSCustomObject]@{ login = if ($_ % 2 -eq 0) { 'coderabbitai' } else { 'cursor[bot]' } }
            html_url = "https://github.com/test/$_"
        }
    }

    Mock Get-PRComments { , $manyComments }
    Mock Get-UnacknowledgedComments { , @() }

    # Act
    $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

    # Assert - Synthesis still triggered
    $synthesisEntry = $results.ActionRequired | Where-Object { $_.Reason -eq 'COPILOT_SYNTHESIS_NEEDED' }
    $synthesisEntry | Should -Not -BeNullOrEmpty
    $synthesisEntry.CommentsToSynthesize | Should -Be 100
}

It 'Rjmurillo-bot as reviewer on non-copilot PR does not trigger synthesis' {
    # Arrange - rjmurillo-bot is reviewer but author is NOT copilot
    Mock Get-BotAuthorInfo { @{ IsBot = $true; Category = 'agent-controlled'; Action = 'pr-comment-responder'; Mention = $null } }
    Mock Resolve-PRConflicts { return $true }
    Mock Get-OpenPRs {
        , @([PSCustomObject]@{
            number = 700
            title = 'Non-copilot bot PR'
            author = [PSCustomObject]@{ login = 'renovate[bot]' }
            reviewDecision = 'CHANGES_REQUESTED'
            mergeable = 'MERGEABLE'
            headRefName = 'feature'
            baseRefName = 'main'
            reviewRequests = @([PSCustomObject]@{ login = 'rjmurillo-bot' })
        })
    }
    Mock Get-PRComments {
        , @([PSCustomObject]@{ id = 1; body = 'Comment'; user = [PSCustomObject]@{ login = 'coderabbitai' } })
    }
    Mock Get-UnacknowledgedComments { , @() }

    # Act
    $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

    # Assert - NO synthesis entry
    $synthesisEntry = $results.ActionRequired | Where-Object { $_.Reason -eq 'COPILOT_SYNTHESIS_NEEDED' }
    $synthesisEntry | Should -BeNullOrEmpty
}
```

**Why Important**: Synthesis logic (lines 1356-1400) has no edge case validation. Could fail with many comments or trigger incorrectly.

---

### 6. Mock Call Verification

**Current State**: Mocks defined but never verified.

**Proposed Enhancement**:

```powershell
It 'Acknowledges all unaddressed comments exactly once' {
    # Arrange - 3 unaddressed comments
    Mock Get-BotAuthorInfo { @{ IsBot = $true; Category = 'agent-controlled'; Action = 'pr-comment-responder'; Mention = $null } }
    Mock Resolve-PRConflicts { return $true }
    Mock Get-OpenPRs {
        , @([PSCustomObject]@{
            number = 800
            title = 'PR with 3 unaddressed comments'
            author = [PSCustomObject]@{ login = 'rjmurillo-bot' }
            reviewDecision = $null
            mergeable = 'MERGEABLE'
            headRefName = 'feature'
            baseRefName = 'main'
            reviewRequests = @()
        })
    }
    Mock Get-PRComments { , @() }
    Mock Get-UnacknowledgedComments {
        , @(
            [PSCustomObject]@{ id = 1; body = 'Comment 1'; user = [PSCustomObject]@{ login = 'coderabbitai' } }
            [PSCustomObject]@{ id = 2; body = 'Comment 2'; user = [PSCustomObject]@{ login = 'cursor[bot]' } }
            [PSCustomObject]@{ id = 3; body = 'Comment 3'; user = [PSCustomObject]@{ login = 'gemini-code-assist' } }
        )
    }
    Mock Add-CommentReaction { return $true }

    # Act
    $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

    # Assert - Add-CommentReaction called exactly 3 times
    Should -Invoke Add-CommentReaction -Times 3 -Exactly

    # Assert - Called with correct comment IDs
    Should -Invoke Add-CommentReaction -ParameterFilter { $CommentId -eq 1 } -Times 1
    Should -Invoke Add-CommentReaction -ParameterFilter { $CommentId -eq 2 } -Times 1
    Should -Invoke Add-CommentReaction -ParameterFilter { $CommentId -eq 3 } -Times 1
}
```

**Why Important**: Without call verification, tests cannot detect if functions are called multiple times (duplicate acknowledgments) or not at all (missed acknowledgments).

---

## P2 Gaps - Nice to Have

### 7. Derivative PR Workflow

**Uncovered Code**: ~200 lines (functions Get-DerivativePRs, Get-PRsWithPendingDerivatives, related logic).

**Impact**: Critical feature for preventing orphaned derivative PRs, but completely untested.

**Proposed Tests**: (See session log for detailed test cases)

---

### 8. Error Resilience

**Scenario**: One PR errors during processing, others should continue.

**Current Coverage**: None. No validation of graceful degradation.

**Proposed Test**:

```powershell
It 'Continues processing other PRs when one PR errors' {
    # Arrange - 3 PRs, middle one throws exception
    Mock Get-BotAuthorInfo { @{ IsBot = $true; Category = 'agent-controlled'; Action = 'pr-comment-responder'; Mention = $null } }
    Mock Resolve-PRConflicts { return $true }
    Mock Get-OpenPRs {
        , @(
            [PSCustomObject]@{ number = 901; title = 'PR 1'; author = [PSCustomObject]@{ login = 'rjmurillo-bot' }; reviewDecision = $null; mergeable = 'MERGEABLE'; headRefName = 'f1'; baseRefName = 'main'; reviewRequests = @() }
            [PSCustomObject]@{ number = 902; title = 'PR 2'; author = [PSCustomObject]@{ login = 'rjmurillo-bot' }; reviewDecision = $null; mergeable = 'MERGEABLE'; headRefName = 'f2'; baseRefName = 'main'; reviewRequests = @() }
            [PSCustomObject]@{ number = 903; title = 'PR 3'; author = [PSCustomObject]@{ login = 'rjmurillo-bot' }; reviewDecision = $null; mergeable = 'MERGEABLE'; headRefName = 'f3'; baseRefName = 'main'; reviewRequests = @() }
        )
    }
    Mock Get-PRComments -ParameterFilter { $PRNumber -eq 902 } { throw "API error" }
    Mock Get-PRComments -ParameterFilter { $PRNumber -ne 902 } { , @() }

    # Act
    $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

    # Assert - 2 PRs processed (901, 903), 1 error (902)
    $results.Processed | Should -Be 2
    $results.Errors | Should -HaveCount 1
    $results.Errors[0].PR | Should -Be 902
}
```

**Why Important**: Production will encounter API errors. Script should be resilient.

---

## Summary

**Total Gaps**: 8 (3 P0, 3 P1, 2 P2)

**P0 Actions Required Before Merge**:
1. Fix integration test bug
2. Add multi-PR deduplication test
3. Add conflict + CHANGES_REQUESTED interaction test

**P1 Actions (Follow-up PR Acceptable)**:
4. Add bot category tests (3 categories)
5. Add synthesis edge case tests (2 scenarios)
6. Add mock call verification (1 test)

**P2 Actions (Future Enhancement)**:
7. Add derivative PR workflow tests
8. Add error resilience test

**Coverage Measurement**: Run coverage collection to validate 80% line coverage target.
