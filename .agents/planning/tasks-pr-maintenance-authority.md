# Task List: PR Maintenance Authority Enhancement

**Source**: `.agents/planning/PRD-pr-maintenance-authority.md`
**Generated**: 2025-12-26
**Target Release**: Next

## Summary

| Phase | Task Count | Complexity Total |
|-------|-----------|------------------|
| Phase 1: Core Logic | 3 | S + S + M = M |
| Phase 2: Copilot Detection | 2 | S + M = M |
| Phase 3: Copilot Synthesis | 2 | M + S = M |
| Phase 4: Deduplication | 1 | S |
| Phase 5: Tests | 7 | XS×6 + S = M |
| Phase 6: Documentation | 2 | XS + XS = S |
| **Total** | **17** | **L** |

## Dependency Graph

```text
Phase 1 (1.1, 1.2, 1.3) → Phase 4 (4.1)
Phase 2 (2.1, 2.2) → Phase 3 (3.1, 3.2)
Phase 1-4 → Phase 5 (Tests)
Phase 1-5 → Phase 6 (Documentation)
```

---

## Phase 1: Core Logic (Stories 1-2)

**Goal**: Enable bot-authored PRs to remain actionable instead of blocked, and trigger on unaddressed comments.

### Task 1.1: [CODE] Modify conflict resolution disposition for bot PRs

- **Story**: Story 1
- **Type**: CODE
- **Complexity**: S
- **Objective**: Change conflict resolution logic so bot-authored PRs go to ActionRequired instead of Blocked when automatic resolution fails
- **Files**:
  - `scripts/Invoke-PRMaintenance.ps1` (lines 1359-1372)
- **Acceptance Criteria**:
  - [ ] When `$isAgentControlledBot -eq $true` AND `$pr.mergeable -eq 'CONFLICTING'` AND resolution fails, PR is added to `$results.ActionRequired` (not `$results.Blocked`)
  - [ ] Entry includes `Reason = 'MANUAL_CONFLICT_RESOLUTION'`
  - [ ] Entry includes `Action = '/pr-review to manually resolve conflicts'`
  - [ ] Entry includes `Category = 'agent-controlled'`
  - [ ] When `$isAgentControlledBot -eq $false` (human-authored) AND resolution fails, PR is still added to `$results.Blocked` (existing behavior preserved)
- **Dependencies**: None

**Prompt**:

```text
In scripts/Invoke-PRMaintenance.ps1 around lines 1359-1372, modify the conflict resolution logic:

CURRENT: When Resolve-PRConflicts returns $false, all PRs are added to $results.Blocked.

CHANGE: Add a conditional check for $isAgentControlledBot before adding to Blocked:

if (-not $resolved) {
    if ($isAgentControlledBot) {
        $null = $results.ActionRequired.Add(@{
            PR = $pr.number
            Author = $authorLogin
            Reason = 'MANUAL_CONFLICT_RESOLUTION'
            Title = $pr.title
            Category = 'agent-controlled'
            Action = '/pr-review to manually resolve conflicts'
        })
    } else {
        $null = $results.Blocked.Add(@{
            PR = $pr.number
            Author = $authorLogin
            Reason = 'UNRESOLVABLE_CONFLICTS'
            Title = $pr.title
        })
    }
}

This preserves existing behavior for human-authored PRs while routing bot PRs to ActionRequired.
```

### Task 1.2: [CODE] Add unaddressed comments check before reviewDecision check

- **Story**: Story 2
- **Type**: CODE
- **Complexity**: S
- **Objective**: Trigger action for bot-authored PRs with unaddressed bot comments regardless of reviewDecision state
- **Files**:
  - `scripts/Invoke-PRMaintenance.ps1` (lines 1270-1288)
- **Acceptance Criteria**:
  - [ ] Before line 1273 (`if ($hasChangesRequested)`), add check: `$unacked = Get-UnacknowledgedComments -Owner $Owner -Repo $Repo -PRNumber $pr.number -Comments $comments`
  - [ ] Modify condition to trigger action if `$unacked.Count -gt 0` OR `$hasChangesRequested`
  - [ ] When unaddressed comments exist but reviewDecision is not CHANGES_REQUESTED, use `Reason = 'UNADDRESSED_COMMENTS'`
  - [ ] Add `UnaddressedCount = $unacked.Count` property to ActionRequired entry
  - [ ] Human-authored PRs are NOT affected (no logic change for `$isAgentControlledBot -eq $false`)
- **Dependencies**: None

**Prompt**:

```text
In scripts/Invoke-PRMaintenance.ps1 around lines 1270-1288, modify the action trigger logic:

BEFORE: Action only triggers when $hasChangesRequested is true.

AFTER: Move Get-UnacknowledgedComments call BEFORE the action determination and expand the trigger condition:

# Get unaddressed comments before action determination
$unacked = Get-UnacknowledgedComments -Owner $Owner -Repo $Repo -PRNumber $pr.number -Comments $comments

# Trigger action if CHANGES_REQUESTED OR unaddressed comments exist
$hasUnaddressedComments = $unacked.Count -gt 0
$needsAction = $hasChangesRequested -or $hasUnaddressedComments

if ($needsAction) {
    $reason = if ($hasChangesRequested) { 'CHANGES_REQUESTED' } else { 'UNADDRESSED_COMMENTS' }
    $action = '/pr-review via pr-comment-responder'
    Write-Log "PR #$($pr.number): rjmurillo-bot is $role with $reason -> /pr-review" -Level WARN
    $null = $results.ActionRequired.Add(@{
        PR = $pr.number
        Author = $authorLogin
        Reason = $reason
        Title = $pr.title
        Category = 'agent-controlled'
        Action = $action
        UnaddressedCount = $unacked.Count
    })
}

This applies only within the $isAgentControlledBot block to preserve human PR behavior.
```

### Task 1.3: [CODE] Refactor unaddressed comment detection to avoid duplication

- **Story**: Story 2
- **Type**: CODE
- **Complexity**: M
- **Objective**: Move unaddressed comment detection before action determination to avoid calling Get-UnacknowledgedComments twice
- **Files**:
  - `scripts/Invoke-PRMaintenance.ps1` (lines 1270-1295)
- **Acceptance Criteria**:
  - [ ] Move `$unacked = Get-UnacknowledgedComments...` call to before line 1270 (after bot detection)
  - [ ] Reuse `$unacked` variable in both action determination (Task 1.2) and acknowledgment loop (line 1291)
  - [ ] Remove duplicate call at line 1291 (currently fetches comments twice)
  - [ ] Verify comments are still acknowledged correctly (existing behavior preserved)
  - [ ] No change to logic flow, only performance optimization
- **Dependencies**: Task 1.2 (requires unaddressed comment check to be in place)

**Prompt**:

```text
FILE: /home/richard/ai-agents/scripts/Invoke-PRMaintenance.ps1
LOCATION: Line 1291 (search pattern: "Get-UnacknowledgedComments -Owner")
ACTION: REPLACE duplicate call with variable reuse

After Task 1.2 adds $unacked at ~line 1270, there is a DUPLICATE call at line 1291.

SEARCH for this EXACT pattern at line 1291:
$unacked = Get-UnacknowledgedComments -Owner $Owner -Repo $Repo -PRNumber $pr.number -Comments $comments
foreach ($comment in $unacked) {

REPLACE WITH (remove the duplicate call, reuse existing $unacked):
# Reuse $unacked from action determination (line ~1270) - avoid duplicate API call
foreach ($comment in $unacked) {

VERIFY: Run `grep -n "Get-UnacknowledgedComments" scripts/Invoke-PRMaintenance.ps1`
- Should appear at function definition (line 436)
- Should appear exactly ONCE in the $isAgentControlledBot block (~line 1270)
- Should NOT appear at line 1291 anymore
```

---

## Phase 2: Copilot Detection (Story 3a)

**Goal**: Identify copilot-swe-agent PRs requiring synthesis and collect other bot comments.

### Task 2.1: [CODE] Add copilot PR detection logic

- **Story**: Story 3a
- **Type**: CODE
- **Complexity**: S
- **Objective**: Detect when rjmurillo-bot is reviewing a copilot-swe-agent PR
- **Files**:
  - `scripts/Invoke-PRMaintenance.ps1` (new logic after line 1267)
- **Acceptance Criteria**:
  - [ ] Add detection: `$isCopilotPR = ($botInfo.Category -eq 'mention-triggered') -and ($authorLogin -match 'copilot')`
  - [ ] Pattern match accepts 'copilot', 'copilot-swe-agent', or similar variations (case-insensitive)
  - [ ] Only trigger when `$isBotReviewer -eq $true` (rjmurillo-bot is reviewer)
  - [ ] Detection happens after line 1262 (`$hasChangesRequested` assignment)
  - [ ] No action taken yet (detection only)
- **Dependencies**: None

**Prompt**:

```text
In scripts/Invoke-PRMaintenance.ps1, add copilot PR detection after line 1262 (after $hasChangesRequested assignment):

# Detect if this is a copilot-swe-agent PR that rjmurillo-bot is reviewing
$isCopilotPR = $false
if ($isBotReviewer -and ($authorLogin -match 'copilot')) {
    # Check if bot category is mention-triggered (copilot-swe-agent behavior)
    $authorBotInfo = Get-BotInfo -Login $authorLogin
    if ($authorBotInfo.Category -eq 'mention-triggered') {
        $isCopilotPR = $true
        Write-Log "PR #$($pr.number): Detected copilot-swe-agent PR with rjmurillo-bot as reviewer" -Level INFO
    }
}

Place this after the $hasChangesRequested assignment but before any action determination logic.
This detection is used by Task 2.2 to collect bot comments for synthesis.
```

### Task 2.2: [CODE] Collect non-copilot bot comments for synthesis

- **Story**: Story 3a
- **Type**: CODE
- **Complexity**: M
- **Objective**: Collect comments from other bots (not copilot) when copilot PR is detected
- **Files**:
  - `scripts/Invoke-PRMaintenance.ps1` (new logic after Task 2.1)
- **Acceptance Criteria**:
  - [ ] When `$isCopilotPR -eq $true`, filter comments: `$otherBotComments = @($comments | Where-Object { $_.user.login -match '(coderabbitai|cursor\[bot\]|gemini-code-assist)' -and $_.user.login -notmatch 'copilot' })`
  - [ ] Count other bot comments: `$commentsToSynthesize = $otherBotComments.Count`
  - [ ] If `$commentsToSynthesize -gt 0`, add to ActionRequired with `Reason = 'COPILOT_SYNTHESIS_NEEDED'`
  - [ ] If `$commentsToSynthesize -eq 0`, do NOT add to ActionRequired for synthesis (no action needed)
  - [ ] Include `CommentsToSynthesize = $commentsToSynthesize` property in ActionRequired entry
  - [ ] Include `Category = 'synthesis-required'` in ActionRequired entry
- **Dependencies**: Task 2.1 (requires copilot detection)

**Prompt**:

```text
FILE: /home/richard/ai-agents/scripts/Invoke-PRMaintenance.ps1
LOCATION: After Task 2.1's $isCopilotPR detection (~line 1268), BEFORE action determination (~line 1270)
SEARCH PATTERN: "if ($isCopilotPR)" (added by Task 2.1)
ACTION: INSERT inside the $isCopilotPR block

INSERT this code block inside the if ($isCopilotPR) { ... } block from Task 2.1:

    # Collect comments from other review bots (not copilot) - CASE-INSENSITIVE
    $otherBotComments = @($comments | Where-Object {
        $_.user.login -imatch '(coderabbitai|cursor\[bot\]|gemini-code-assist)' -and
        $_.user.login -inotmatch 'copilot'
    })
    $commentsToSynthesize = $otherBotComments.Count

    if ($commentsToSynthesize -gt 0) {
        Write-Log "PR #$($pr.number): Found $commentsToSynthesize comments from other bots to synthesize" -Level INFO
        $null = $results.ActionRequired.Add(@{
            PR = $pr.number
            Author = $authorLogin
            Reason = 'COPILOT_SYNTHESIS_NEEDED'
            Title = $pr.title
            Category = 'synthesis-required'
            Action = 'Synthesize bot feedback and direct to @copilot'
            CommentsToSynthesize = $commentsToSynthesize
        })
    } else {
        Write-Log "PR #$($pr.number): Copilot PR with no other bot comments - no synthesis needed" -Level INFO
    }

NOTE: Uses -imatch and -inotmatch for CASE-INSENSITIVE matching (handles CodeRabbitAI vs coderabbitai).
VERIFY: If $commentsToSynthesize is 0, do NOT add to ActionRequired (only log message).
```

---

## Phase 3: Copilot Synthesis (Story 3b)

**Goal**: Generate and post @copilot synthesis prompts for copilot PRs with bot feedback.

### Task 3.1: [CODE] Create Invoke-CopilotSynthesis function

- **Story**: Story 3b
- **Type**: CODE
- **Complexity**: M
- **Objective**: Implement function to generate markdown synthesis prompt from bot comments
- **Files**:
  - `scripts/Invoke-PRMaintenance.ps1` (new function before main workflow)
- **Acceptance Criteria**:
  - [ ] Function signature: `function Invoke-CopilotSynthesis { param($Owner, $Repo, $PRNumber, $PRTitle, $BotComments) }`
  - [ ] Generate prompt starting with: `@copilot Please address the following feedback on PR #$PRNumber:`
  - [ ] Group comments by bot author (coderabbitai, cursor[bot], gemini-code-assist)
  - [ ] For each bot, list comment count and include links: `- [Comment text](comment.html_url)`
  - [ ] End with: `Please implement fixes for these issues and update the PR.`
  - [ ] Return formatted markdown string
  - [ ] Handle edge case: if only 1 bot has comments, still generate synthesis (no minimum threshold)
- **Dependencies**: Task 2.2 (requires comment collection)

**Prompt**:

```text
In scripts/Invoke-PRMaintenance.ps1, add this function before the main workflow (around line 100):

function Invoke-CopilotSynthesis {
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$PRNumber,
        [string]$PRTitle,
        [array]$BotComments
    )

    $prompt = "@copilot Please address the following feedback on PR #$PRNumber`:`n`n"

    # Group comments by bot author
    $grouped = $BotComments | Group-Object { $_.user.login }

    foreach ($group in $grouped) {
        $botName = $group.Name
        $comments = $group.Group
        $prompt += "**$botName** ($($comments.Count) comment$(if($comments.Count -gt 1){'s'})):`n"

        foreach ($comment in $comments) {
            # Truncate body to first 100 chars for link text
            $linkText = if ($comment.body.Length -gt 100) {
                $comment.body.Substring(0, 97) + '...'
            } else { $comment.body }
            $linkText = $linkText -replace '[\r\n]+', ' '
            $prompt += "- [$linkText]($($comment.html_url))`n"
        }
        $prompt += "`n"
    }

    $prompt += "Please implement fixes for these issues and update the PR."
    return $prompt
}

This function groups comments by bot author and generates a markdown prompt for @copilot.
```

### Task 3.2: [CODE] Post synthesis prompt as PR comment

- **Story**: Story 3b
- **Type**: CODE
- **Complexity**: S
- **Objective**: Post generated synthesis prompt to copilot PR via gh CLI
- **Files**:
  - `scripts/Invoke-PRMaintenance.ps1` (new logic after Task 2.2)
- **Acceptance Criteria**:
  - [ ] When `$commentsToSynthesize -gt 0`, call `$synthesisPrompt = Invoke-CopilotSynthesis -Owner $Owner -Repo $Repo -PRNumber $pr.number -PRTitle $pr.title -BotComments $otherBotComments`
  - [ ] Post comment: `gh pr comment $pr.number --repo "$Owner/$Repo" --body $synthesisPrompt`
  - [ ] Log action: `Write-Log "Posted copilot synthesis for PR #$($pr.number)" -Level ACTION`
  - [ ] Handle failure: if `gh pr comment` fails, log error but continue processing
  - [ ] Synthesis only triggers once per PR per maintenance run (no duplicate comments)
- **Dependencies**: Task 3.1 (requires synthesis function)

**Prompt**:

```text
FILE: /home/richard/ai-agents/scripts/Invoke-PRMaintenance.ps1
ACTION: Two modifications required

## STEP 1: Add SynthesisPosted counter to $results initialization

LOCATION: Line 1180 (search pattern: "$results = @{")
INSERT new property after "Errors = [System.Collections.ArrayList]::new()":

        SynthesisPosted = 0

So it becomes:
    $results = @{
        TotalPRs = 0
        Processed = 0
        CommentsAcknowledged = 0
        ConflictsResolved = 0
        Blocked = [System.Collections.ArrayList]::new()
        ActionRequired = [System.Collections.ArrayList]::new()
        DerivativePRs = [System.Collections.ArrayList]::new()
        ParentsWithDerivatives = [System.Collections.ArrayList]::new()
        Errors = [System.Collections.ArrayList]::new()
        SynthesisPosted = 0  # <-- ADD THIS LINE
    }

## STEP 2: Add synthesis posting inside Task 2.2 block

LOCATION: Inside the "if ($commentsToSynthesize -gt 0)" block from Task 2.2
INSERT BEFORE the $results.ActionRequired.Add() call:

    # Generate and post synthesis prompt
    $synthesisPrompt = Invoke-CopilotSynthesis -Owner $Owner -Repo $Repo `
        -PRNumber $pr.number -PRTitle $pr.title -BotComments $otherBotComments

    try {
        $null = gh pr comment $pr.number --repo "$Owner/$Repo" --body $synthesisPrompt
        Write-Log "Posted copilot synthesis for PR #$($pr.number)" -Level ACTION
        $results.SynthesisPosted++
    } catch {
        Write-Log "Failed to post synthesis for PR #$($pr.number): $_" -Level ERROR
        # Continue processing - don't fail on synthesis error
    }

VERIFY: Run `grep -n "SynthesisPosted" scripts/Invoke-PRMaintenance.ps1`
- Should appear at line ~1189 (initialization)
- Should appear inside synthesis block (increment)
```

---

## Phase 4: Deduplication (Story 4)

**Goal**: Ensure each PR appears in exactly one status list.

### Task 4.1: [CODE] Implement single list guarantee logic

- **Story**: Story 4
- **Type**: CODE
- **Complexity**: S
- **Objective**: Prevent PRs from appearing in both ActionRequired and Blocked lists
- **Files**:
  - `scripts/Invoke-PRMaintenance.ps1` (lines 1359-1372)
- **Acceptance Criteria**:
  - [ ] Before adding PR to Blocked for conflicts, check: `$alreadyInActionRequired = $results.ActionRequired | Where-Object { $_.PR -eq $pr.number }`
  - [ ] If `$alreadyInActionRequired` exists, update existing entry: `$alreadyInActionRequired.HasConflicts = $true`
  - [ ] Append to Action field: `$alreadyInActionRequired.Action = "$($alreadyInActionRequired.Action) + resolve conflicts"`
  - [ ] Do NOT add PR to Blocked if already in ActionRequired
  - [ ] Priority order: ActionRequired > Blocked (ActionRequired takes precedence)
  - [ ] Verify no PR appears in both `$results.ActionRequired` and `$results.Blocked` after processing
- **Dependencies**: Tasks 1.1, 1.2, 2.2 (requires all ActionRequired additions to be in place)

**Prompt**:

```text
In scripts/Invoke-PRMaintenance.ps1, modify the conflict resolution block (lines 1359-1372) to implement single list guarantee:

REPLACE the conflict resolution else block with:

if (-not $resolved) {
    # Check if PR already in ActionRequired (deduplication)
    $alreadyInActionRequired = $results.ActionRequired | Where-Object { $_.PR -eq $pr.number }

    if ($alreadyInActionRequired) {
        # Update existing ActionRequired entry with conflict info
        $alreadyInActionRequired.HasConflicts = $true
        $alreadyInActionRequired.Action = "$($alreadyInActionRequired.Action) + resolve conflicts"
        Write-Log "PR #$($pr.number): Added conflict info to existing ActionRequired entry" -Level INFO
    }
    elseif ($isAgentControlledBot) {
        # Bot PR not yet in ActionRequired - add it
        $null = $results.ActionRequired.Add(@{
            PR = $pr.number
            Author = $authorLogin
            Reason = 'MANUAL_CONFLICT_RESOLUTION'
            Title = $pr.title
            Category = 'agent-controlled'
            Action = '/pr-review to manually resolve conflicts'
        })
    }
    else {
        # Human-authored PR - add to Blocked
        $null = $results.Blocked.Add(@{
            PR = $pr.number
            Author = $authorLogin
            Reason = 'UNRESOLVABLE_CONFLICTS'
            Title = $pr.title
        })
    }
}

This ensures no PR appears in both ActionRequired and Blocked lists.
```

---

## Phase 5: Tests

**Goal**: Verify all functional requirements with unit and integration tests.

### Task 5.1: [TEST] Bot PR conflicts go to ActionRequired

- **Story**: Story 1
- **Type**: TEST
- **Complexity**: XS
- **Objective**: Verify bot-authored PRs with conflicts are added to ActionRequired (not Blocked)
- **Files**:
  - `tests/Invoke-PRMaintenance.Tests.ps1` (new test case)
- **Acceptance Criteria**:
  - [ ] Mock PR: author = 'rjmurillo-bot', mergeable = 'CONFLICTING', Resolve-PRConflicts returns $false
  - [ ] Verify PR in `$results.ActionRequired` with Reason = 'MANUAL_CONFLICT_RESOLUTION'
  - [ ] Verify PR NOT in `$results.Blocked`
  - [ ] Verify Action = '/pr-review to manually resolve conflicts'
- **Dependencies**: Task 1.1 (requires conflict disposition logic)

**Prompt**:

```text
FILE: /home/richard/ai-agents/tests/Invoke-PRMaintenance.Tests.ps1
STATUS: FILE DOES NOT EXIST - must be created

CREATE the test file with this structure:

BeforeAll {
    . "$PSScriptRoot/../scripts/Invoke-PRMaintenance.ps1"
}

Describe 'Invoke-PRMaintenance Bot Authority Tests' {
    BeforeEach {
        # Mock GitHub CLI and external dependencies
        Mock gh { }
        Mock Write-Log { }
    }

    It 'Routes bot-authored PR with unresolvable conflicts to ActionRequired' {
        # Arrange
        Mock Get-BotInfo { @{ IsBot = $true; Category = 'agent-controlled'; IsReviewBot = $true } }
        Mock Resolve-PRConflicts { return $false }
        Mock Get-OpenPRs {
            @([PSCustomObject]@{
                number = 999
                title = 'Test PR'
                author = @{ login = 'rjmurillo-bot' }
                mergeable = 'CONFLICTING'
                headRefName = 'test-branch'
                baseRefName = 'main'
                reviewDecision = $null
                reviewRequests = @()
            })
        }
        Mock Get-PRComments { @() }

        # Act
        $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

        # Assert
        $results.ActionRequired | Should -HaveCount 1
        $results.ActionRequired[0].Reason | Should -Be 'MANUAL_CONFLICT_RESOLUTION'
        $results.ActionRequired[0].Action | Should -Be '/pr-review to manually resolve conflicts'
        $results.Blocked | Should -BeNullOrEmpty
    }
}

NOTE: Tests mock Get-OpenPRs and call Invoke-PRMaintenance directly (no Process-SinglePR function exists).
VERIFY: Run `Invoke-Pester tests/Invoke-PRMaintenance.Tests.ps1 -Output Detailed`
```

### Task 5.2: [TEST] Bot PR unaddressed comments trigger action

- **Story**: Story 2
- **Type**: TEST
- **Complexity**: XS
- **Objective**: Verify bot-authored PRs with unaddressed comments trigger action regardless of reviewDecision
- **Files**:
  - `tests/Invoke-PRMaintenance.Tests.ps1` (new test case)
- **Acceptance Criteria**:
  - [ ] Mock PR: author = 'rjmurillo-bot', reviewDecision = $null, Get-UnacknowledgedComments returns 3 comments
  - [ ] Verify PR in `$results.ActionRequired` with Reason = 'UNADDRESSED_COMMENTS'
  - [ ] Verify UnaddressedCount = 3
  - [ ] Verify Action = '/pr-review via pr-comment-responder'
- **Dependencies**: Task 1.2 (requires unaddressed comments check)

**Prompt**:

```text
FILE: /home/richard/ai-agents/tests/Invoke-PRMaintenance.Tests.ps1
PREREQUISITE: File created by Task 5.1
ACTION: ADD test to existing 'Invoke-PRMaintenance Bot Authority Tests' Describe block

    It 'Triggers action for bot PR with unaddressed comments even without CHANGES_REQUESTED' {
        # Arrange
        Mock Get-BotInfo { @{ IsBot = $true; Category = 'agent-controlled'; IsReviewBot = $true } }
        Mock Resolve-PRConflicts { return $true }  # No conflicts
        Mock Get-OpenPRs {
            @([PSCustomObject]@{
                number = 888
                title = 'Test PR with comments'
                author = @{ login = 'rjmurillo-bot' }
                reviewDecision = $null  # Not CHANGES_REQUESTED
                mergeable = 'MERGEABLE'
                headRefName = 'feature'
                baseRefName = 'main'
                reviewRequests = @()
            })
        }
        Mock Get-PRComments { @() }
        Mock Get-UnacknowledgedComments {
            @(
                @{ id = 1; body = 'Comment 1'; user = @{ login = 'coderabbitai' } }
                @{ id = 2; body = 'Comment 2'; user = @{ login = 'cursor[bot]' } }
                @{ id = 3; body = 'Comment 3'; user = @{ login = 'gemini-code-assist' } }
            )
        }

        # Act
        $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

        # Assert
        $results.ActionRequired | Should -HaveCount 1
        $results.ActionRequired[0].Reason | Should -Be 'UNADDRESSED_COMMENTS'
        $results.ActionRequired[0].UnaddressedCount | Should -Be 3
        $results.ActionRequired[0].Action | Should -Be '/pr-review via pr-comment-responder'
    }

VERIFY: Run `Invoke-Pester tests/Invoke-PRMaintenance.Tests.ps1 -Output Detailed`
```

### Task 5.3: [TEST] Copilot PR synthesis detection

- **Story**: Story 3a
- **Type**: TEST
- **Complexity**: XS
- **Objective**: Verify copilot-swe-agent PRs with other bot comments trigger COPILOT_SYNTHESIS_NEEDED
- **Files**:
  - `tests/Invoke-PRMaintenance.Tests.ps1` (new test case)
- **Acceptance Criteria**:
  - [ ] Mock PR: author = 'copilot-swe-agent', reviewer = 'rjmurillo-bot', comments from 'coderabbitai' (3) and 'cursor[bot]' (2)
  - [ ] Verify PR in `$results.ActionRequired` with Reason = 'COPILOT_SYNTHESIS_NEEDED'
  - [ ] Verify CommentsToSynthesize = 5
  - [ ] Verify Category = 'synthesis-required'
- **Dependencies**: Task 2.2 (requires comment collection)

**Prompt**:

```text
FILE: /home/richard/ai-agents/tests/Invoke-PRMaintenance.Tests.ps1
PREREQUISITE: File created by Task 5.1
ACTION: ADD test to existing 'Invoke-PRMaintenance Bot Authority Tests' Describe block

    It 'Detects copilot PR and triggers synthesis for other bot comments' {
        # Arrange
        Mock Get-BotInfo -ParameterFilter { $Login -eq 'copilot-swe-agent' } {
            @{ IsBot = $true; Category = 'mention-triggered' }
        }
        Mock Get-BotInfo -ParameterFilter { $Login -ne 'copilot-swe-agent' } {
            @{ IsBot = $true; Category = 'agent-controlled'; IsReviewBot = $true }
        }
        Mock Test-IsBotReviewer { return $true }  # rjmurillo-bot is reviewer
        Mock Resolve-PRConflicts { return $true }
        Mock Get-OpenPRs {
            @([PSCustomObject]@{
                number = 247
                title = 'Copilot PR'
                author = @{ login = 'copilot-swe-agent' }
                reviewDecision = 'CHANGES_REQUESTED'
                mergeable = 'MERGEABLE'
                headRefName = 'feature'
                baseRefName = 'main'
                reviewRequests = @(@{ login = 'rjmurillo-bot' })
            })
        }
        Mock Get-PRComments {
            @(
                @{ id = 1; body = 'Issue 1'; user = @{ login = 'coderabbitai' }; html_url = 'https://...' }
                @{ id = 2; body = 'Issue 2'; user = @{ login = 'coderabbitai' }; html_url = 'https://...' }
                @{ id = 3; body = 'Issue 3'; user = @{ login = 'cursor[bot]' }; html_url = 'https://...' }
            )
        }
        Mock gh { }  # Mock synthesis comment posting

        # Act
        $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

        # Assert
        $synthesisEntry = $results.ActionRequired | Where-Object { $_.Reason -eq 'COPILOT_SYNTHESIS_NEEDED' }
        $synthesisEntry | Should -Not -BeNullOrEmpty
        $synthesisEntry.CommentsToSynthesize | Should -Be 3
        $synthesisEntry.Category | Should -Be 'synthesis-required'
    }

VERIFY: Run `Invoke-Pester tests/Invoke-PRMaintenance.Tests.ps1 -Output Detailed`
```

### Task 5.4: [TEST] No duplicate PR entries

- **Story**: Story 4
- **Type**: TEST
- **Complexity**: XS
- **Objective**: Verify PRs with conflicts AND CHANGES_REQUESTED appear in ActionRequired only (not both lists)
- **Files**:
  - `tests/Invoke-PRMaintenance.Tests.ps1` (new test case)
- **Acceptance Criteria**:
  - [ ] Mock PR: author = 'rjmurillo-bot', reviewDecision = 'CHANGES_REQUESTED', mergeable = 'CONFLICTING', Resolve-PRConflicts returns $false
  - [ ] Verify PR in `$results.ActionRequired` exactly once
  - [ ] Verify PR NOT in `$results.Blocked`
  - [ ] Verify HasConflicts = $true on ActionRequired entry
  - [ ] Verify Action includes both '/pr-review' and 'resolve conflicts'
- **Dependencies**: Task 4.1 (requires deduplication logic)

**Prompt**:

```text
FILE: /home/richard/ai-agents/tests/Invoke-PRMaintenance.Tests.ps1
PREREQUISITE: File created by Task 5.1
ACTION: ADD test to existing 'Invoke-PRMaintenance Bot Authority Tests' Describe block

    It 'PR with conflicts and CHANGES_REQUESTED appears in ActionRequired only (deduplication)' {
        # Arrange
        Mock Get-BotInfo { @{ IsBot = $true; Category = 'agent-controlled'; IsReviewBot = $true } }
        Mock Resolve-PRConflicts { return $false }  # Conflict resolution fails
        Mock Get-OpenPRs {
            @([PSCustomObject]@{
                number = 235
                title = 'Bot PR with conflicts and changes requested'
                author = @{ login = 'rjmurillo-bot' }
                reviewDecision = 'CHANGES_REQUESTED'
                mergeable = 'CONFLICTING'
                headRefName = 'feature-branch'
                baseRefName = 'main'
                reviewRequests = @()
            })
        }
        Mock Get-PRComments { @() }
        Mock Get-UnacknowledgedComments { @() }

        # Act
        $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

        # Assert - Single entry in ActionRequired (not duplicated)
        $prEntries = $results.ActionRequired | Where-Object { $_.PR -eq 235 }
        $prEntries | Should -HaveCount 1

        # Assert - Not in Blocked
        $results.Blocked | Where-Object { $_.PR -eq 235 } | Should -BeNullOrEmpty

        # Assert - Has conflict info merged
        $prEntries[0].HasConflicts | Should -Be $true
        $prEntries[0].Action | Should -Match 'resolve conflicts'
    }

VERIFY: Run `Invoke-Pester tests/Invoke-PRMaintenance.Tests.ps1 -Output Detailed`
```

### Task 5.5: [TEST] Human PR conflicts go to Blocked

- **Story**: Story 1
- **Type**: TEST
- **Complexity**: XS
- **Objective**: Verify human-authored PRs with conflicts are still added to Blocked (existing behavior)
- **Files**:
  - `tests/Invoke-PRMaintenance.Tests.ps1` (new test case)
- **Acceptance Criteria**:
  - [ ] Mock PR: author = 'human-user', mergeable = 'CONFLICTING', Resolve-PRConflicts returns $false
  - [ ] Verify PR in `$results.Blocked` with Reason = 'UNRESOLVABLE_CONFLICTS'
  - [ ] Verify PR NOT in `$results.ActionRequired`
  - [ ] Verify no regression to existing human PR handling
- **Dependencies**: Task 1.1 (requires conflict disposition logic)

**Prompt**:

```text
FILE: /home/richard/ai-agents/tests/Invoke-PRMaintenance.Tests.ps1
PREREQUISITE: File created by Task 5.1
ACTION: ADD test to existing 'Invoke-PRMaintenance Bot Authority Tests' Describe block

    It 'Human-authored PR with unresolvable conflicts goes to Blocked (not ActionRequired)' {
        # Arrange - REGRESSION TEST for human PR handling
        Mock Get-BotInfo { @{ IsBot = $false } }  # Not a bot
        Mock Resolve-PRConflicts { return $false }  # Conflict resolution fails
        Mock Get-OpenPRs {
            @([PSCustomObject]@{
                number = 777
                title = 'Human PR'
                author = @{ login = 'human-user' }
                mergeable = 'CONFLICTING'
                headRefName = 'feature'
                baseRefName = 'main'
                reviewDecision = $null
                reviewRequests = @()
            })
        }
        Mock Get-PRComments { @() }

        # Act
        $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

        # Assert - Human PR goes to Blocked (existing behavior preserved)
        $results.Blocked | Should -HaveCount 1
        $results.Blocked[0].Reason | Should -Be 'UNRESOLVABLE_CONFLICTS'
        $results.Blocked[0].PR | Should -Be 777

        # Assert - NOT in ActionRequired
        $results.ActionRequired | Where-Object { $_.PR -eq 777 } | Should -BeNullOrEmpty
    }

NOTE: This is a REGRESSION test ensuring human PRs still go to Blocked (not affected by bot authority changes).
VERIFY: Run `Invoke-Pester tests/Invoke-PRMaintenance.Tests.ps1 -Output Detailed`
```

### Task 5.6: [TEST] Copilot PR with zero other bot comments

- **Story**: Story 3a
- **Type**: TEST
- **Complexity**: XS
- **Objective**: Verify copilot PRs with 0 other bot comments do NOT trigger COPILOT_SYNTHESIS_NEEDED
- **Files**:
  - `tests/Invoke-PRMaintenance.Tests.ps1` (new test case)
- **Acceptance Criteria**:
  - [ ] Mock PR: author = 'copilot-swe-agent', reviewer = 'rjmurillo-bot', comments only from copilot (no other bots)
  - [ ] Verify PR NOT in `$results.ActionRequired` with Reason = 'COPILOT_SYNTHESIS_NEEDED'
  - [ ] Verify CommentsToSynthesize = 0 or not set
  - [ ] Edge case: no synthesis triggered when no other bot feedback exists
- **Dependencies**: Task 2.2 (requires comment collection)

**Prompt**:

```text
FILE: /home/richard/ai-agents/tests/Invoke-PRMaintenance.Tests.ps1
PREREQUISITE: File created by Task 5.1
ACTION: ADD test to existing 'Invoke-PRMaintenance Bot Authority Tests' Describe block

    It 'Copilot PR with no other bot comments does NOT trigger synthesis' {
        # Arrange - EDGE CASE: No other bot comments to synthesize
        Mock Get-BotInfo -ParameterFilter { $Login -eq 'copilot-swe-agent' } {
            @{ IsBot = $true; Category = 'mention-triggered' }
        }
        Mock Get-BotInfo -ParameterFilter { $Login -ne 'copilot-swe-agent' } {
            @{ IsBot = $true; Category = 'agent-controlled'; IsReviewBot = $true }
        }
        Mock Test-IsBotReviewer { return $true }
        Mock Resolve-PRConflicts { return $true }
        Mock Get-OpenPRs {
            @([PSCustomObject]@{
                number = 333
                title = 'Copilot PR without other bot feedback'
                author = @{ login = 'copilot-swe-agent' }
                reviewDecision = 'APPROVED'
                mergeable = 'MERGEABLE'
                headRefName = 'feature'
                baseRefName = 'main'
                reviewRequests = @(@{ login = 'rjmurillo-bot' })
            })
        }
        # Only copilot's own comments - no other bots
        Mock Get-PRComments {
            @(@{ id = 1; body = 'I fixed it'; user = @{ login = 'copilot-swe-agent' } })
        }

        # Act
        $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

        # Assert - NO synthesis entry (0 other bot comments)
        $synthesisEntry = $results.ActionRequired | Where-Object { $_.Reason -eq 'COPILOT_SYNTHESIS_NEEDED' }
        $synthesisEntry | Should -BeNullOrEmpty
    }

NOTE: EDGE CASE test - synthesis should NOT trigger when no other bots left feedback.
VERIFY: Run `Invoke-Pester tests/Invoke-PRMaintenance.Tests.ps1 -Output Detailed`
```

### Task 5.7: [TEST] Integration test on 6 affected PRs

- **Story**: All stories
- **Type**: TEST
- **Complexity**: S
- **Objective**: Run Invoke-PRMaintenance against real PR set and verify correct dispositions
- **Files**:
  - `tests/Integration-PRMaintenance.Tests.ps1` (new integration test)
- **Acceptance Criteria**:
  - [ ] Run against PRs: #365, #353, #301, #255, #247, #235 (from PRD)
  - [ ] Verify bot-authored PRs with conflicts appear in ActionRequired (not Blocked)
  - [ ] Verify unaddressed comments trigger action regardless of reviewDecision
  - [ ] Verify PR #247 (copilot-swe-agent) receives @copilot synthesis if applicable
  - [ ] Verify no PR appears in both ActionRequired and Blocked
  - [ ] Integration test uses real data (not mocks)
- **Dependencies**: Tasks 1.1, 1.2, 2.2, 3.2, 4.1 (requires all code changes)

**Prompt**:

```text
FILE: /home/richard/ai-agents/tests/Integration-PRMaintenance.Tests.ps1
STATUS: FILE DOES NOT EXIST - must be created
ACTION: CREATE new integration test file

NOTE: These tests run against LIVE GitHub API data. PRs may be closed/merged.
Skip tests if PRs are no longer open.

CREATE the integration test file:

BeforeAll {
    . "$PSScriptRoot/../scripts/Invoke-PRMaintenance.ps1"
    $script:Owner = 'rjmurillo'
    $script:Repo = 'ai-agents'

    # Discover which affected PRs are still open (avoid hardcoding)
    $script:AffectedBotPRs = @(365, 353, 301, 255, 235)
    $script:CopilotPR = 247
}

Describe 'Invoke-PRMaintenance Integration Tests' -Tag 'Integration' {
    BeforeEach {
        # Check if PRs are still open, skip if closed
        $openPRs = gh pr list --repo "$Owner/$Repo" --state open --json number | ConvertFrom-Json
        $script:OpenPRNumbers = $openPRs.number
    }

    It 'Bot-authored PRs with conflicts appear in ActionRequired (not Blocked)' -Skip:(-not ($OpenPRNumbers | Where-Object { $_ -in $AffectedBotPRs })) {
        # Run maintenance on affected PRs that are still open
        $prsToTest = $AffectedBotPRs | Where-Object { $_ -in $OpenPRNumbers }
        if (-not $prsToTest) {
            Set-ItResult -Skipped -Because "No affected bot PRs are currently open"
            return
        }

        $results = Invoke-PRMaintenance -Owner $Owner -Repo $Repo

        foreach ($prNum in $prsToTest) {
            $inActionRequired = $results.ActionRequired | Where-Object { $_.PR -eq $prNum }
            $inBlocked = $results.Blocked | Where-Object { $_.PR -eq $prNum }

            $inActionRequired | Should -Not -BeNullOrEmpty -Because "PR #$prNum should be in ActionRequired"
            $inBlocked | Should -BeNullOrEmpty -Because "PR #$prNum should NOT be in Blocked"
        }
    }

    It 'PR #247 (copilot PR) triggers synthesis workflow' -Skip:($CopilotPR -notin $OpenPRNumbers) {
        $results = Invoke-PRMaintenance -Owner $Owner -Repo $Repo

        $copilotEntry = $results.ActionRequired | Where-Object { $_.PR -eq $CopilotPR }
        $copilotEntry.Reason | Should -Be 'COPILOT_SYNTHESIS_NEEDED'
    }

    It 'No PR appears in both ActionRequired and Blocked' {
        $results = Invoke-PRMaintenance -Owner $Owner -Repo $Repo

        foreach ($actionItem in $results.ActionRequired) {
            $duplicate = $results.Blocked | Where-Object { $_.PR -eq $actionItem.PR }
            $duplicate | Should -BeNullOrEmpty -Because "PR #$($actionItem.PR) should not be in both lists"
        }
    }
}

VERIFY: Run `Invoke-Pester tests/Integration-PRMaintenance.Tests.ps1 -Tag Integration -Output Detailed`
NOTE: Requires GitHub CLI authentication. Some tests may skip if PRs are closed.
```

---

## Phase 6: Documentation

**Goal**: Update protocol documentation and memory files.

### Task 6.1: [DOCS] Update bot-author-feedback-protocol.md

- **Story**: Story 3b
- **Type**: DOCS
- **Complexity**: XS
- **Objective**: Document copilot synthesis workflow in protocol
- **Files**:
  - `.agents/architecture/bot-author-feedback-protocol.md`
- **Acceptance Criteria**:
  - [ ] Add row to Activation Triggers table (line 133): "Reviewer on Copilot PR | rjmurillo-bot reviews copilot-swe-agent PR | N/A | Synthesize bot feedback for @copilot"
  - [ ] Add section "Copilot Synthesis Workflow" after line 200
  - [ ] Document when synthesis triggers (rjmurillo-bot reviewer + copilot-swe-agent author + other bot comments)
  - [ ] Document synthesis format (markdown prompt with bot feedback grouped by author)
  - [ ] Define bot authority boundary: "Bot reviewer CANNOT directly modify mention-triggered PRs - must delegate via @copilot"
- **Dependencies**: Task 3.2 (requires synthesis implementation)

**Prompt**:

```text
FILE: /home/richard/ai-agents/.agents/architecture/bot-author-feedback-protocol.md
ACTION: Two modifications required

## STEP 1: Add row to Activation Triggers table

SEARCH PATTERN: "| Trigger | Condition |" or "| **PR Author** |"
LOCATION: Line ~133 (inside the activation triggers table)

ADD this row after the existing "Reviewer" rows:
| **Reviewer on Copilot PR** | rjmurillo-bot reviews copilot-swe-agent PR | N/A | Synthesize bot feedback for @copilot |

The table should now have 5 rows total (2 Author + 2 Reviewer + 1 Copilot).

## STEP 2: Add new section after the table

SEARCH PATTERN: End of activation triggers table (blank line after last row)
LOCATION: Approximately line 140-145

INSERT this new section:

## Copilot Synthesis Workflow

When rjmurillo-bot is assigned as reviewer on a copilot-swe-agent PR, it synthesizes feedback from other review bots.

### Trigger Conditions

1. PR author matches `copilot` pattern (copilot-swe-agent)
2. rjmurillo-bot is a reviewer on the PR
3. Comments exist from other bots (coderabbitai, cursor[bot], gemini-code-assist)

### Synthesis Format

@copilot prompt includes:
- PR context (number, title)
- Comments grouped by bot author
- Links to each comment
- Clear action request

### Bot Authority Boundary

**CRITICAL**: Bot reviewer CANNOT directly modify mention-triggered PRs.
Must delegate via @copilot mention for copilot-swe-agent to implement changes.

VERIFY: Run `grep -n "Copilot Synthesis" .agents/architecture/bot-author-feedback-protocol.md`
```

### Task 6.2: [DOCS] Update pr-changes-requested-semantics.md memory

- **Story**: Stories 2, 3b
- **Type**: DOCS
- **Complexity**: XS
- **Objective**: Document unaddressed comments trigger and copilot synthesis workflow
- **Files**:
  - `.agents/memories/pr-changes-requested-semantics.md`
- **Acceptance Criteria**:
  - [ ] Add section documenting that unaddressed comments trigger action regardless of reviewDecision
  - [ ] Add section documenting copilot synthesis workflow
  - [ ] Document that bot-authored PRs have different triggers than human-authored PRs
  - [ ] Include examples of UNADDRESSED_COMMENTS and COPILOT_SYNTHESIS_NEEDED reasons
- **Dependencies**: Tasks 1.2, 3.2 (requires implementation of features)

**Prompt**:

```text
FILE: /home/richard/ai-agents/.agents/memories/pr-changes-requested-semantics.md
STATUS: FILE DOES NOT EXIST - must be created
ACTION: CREATE new Serena memory file

CREATE the memory file with this content:

# PR Changes Requested Semantics

This memory documents when PR maintenance triggers action for bot-authored PRs.

## Overview

Bot-authored PRs use expanded trigger conditions beyond just `reviewDecision = CHANGES_REQUESTED`.

## Bot PR Action Triggers (Beyond CHANGES_REQUESTED)

Bot-authored PRs trigger action under expanded conditions:

### UNADDRESSED_COMMENTS Trigger
- **When**: Unaddressed bot comments exist (count > 0)
- **Regardless of**: reviewDecision state (null, APPROVED, etc.)
- **Action**: `/pr-review via pr-comment-responder`
- **Note**: Eyes reaction = acknowledgment only, NOT "addressed"

### COPILOT_SYNTHESIS_NEEDED Trigger
- **When**: rjmurillo-bot reviews copilot-swe-agent PR AND other bots left feedback
- **Action**: Synthesize feedback into @copilot prompt
- **Bots synthesized**: coderabbitai, cursor[bot], gemini-code-assist
- **Note**: Bot reviewer cannot directly modify - must delegate via @copilot

### MANUAL_CONFLICT_RESOLUTION Trigger
- **When**: Bot-authored PR has unresolvable merge conflicts
- **Action**: `/pr-review to manually resolve conflicts`
- **Note**: Bot has full authority over its own PRs

## Action Reasons Reference

| Reason | Trigger | Action |
|--------|---------|--------|
| CHANGES_REQUESTED | reviewDecision = CHANGES_REQUESTED | /pr-review |
| UNADDRESSED_COMMENTS | unacked.Count > 0 | /pr-review via pr-comment-responder |
| MANUAL_CONFLICT_RESOLUTION | Bot PR + failed auto-resolution | /pr-review to resolve conflicts |
| COPILOT_SYNTHESIS_NEEDED | Bot reviewer on copilot PR | Synthesize for @copilot |

## Related Files
- scripts/Invoke-PRMaintenance.ps1
- .agents/architecture/bot-author-feedback-protocol.md

VERIFY: Run `cat .agents/memories/pr-changes-requested-semantics.md` to confirm file creation.
```

---

## Estimate Reconciliation

**Source Document**: PRD-pr-maintenance-authority.md
**Source Estimate**: Not provided in PRD
**Derived Estimate**: 17 tasks, L complexity total
**Difference**: N/A (no source estimate)
**Status**: N/A
**Rationale**: PRD does not include effort estimates. Task breakdown provides granular complexity sizing.

---

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking existing human PR workflow | High | Task 5.5 validates human PR behavior preserved |
| Get-UnacknowledgedComments performance | Medium | Task 1.3 optimizes to single call per PR |
| Copilot synthesis comment spam | Medium | Synthesis only triggers once per run (Task 3.2) |
| gh CLI failure on synthesis post | Low | Task 3.2 includes error handling |
| Deduplication logic complexity | Medium | Task 4.1 uses simple priority order (ActionRequired > Blocked) |

---

## Handoff Validation Checklist

- [x] Tasks document saved to `.agents/planning/tasks-pr-maintenance-authority.md`
- [x] All tasks have unique IDs (Phase.Task format)
- [x] All tasks have acceptance criteria
- [x] All tasks have complexity estimates (XS/S/M/L/XL)
- [x] Dependencies documented and graph included
- [x] Phase groupings logical (Core → Detection → Synthesis → Dedup → Tests → Docs)
- [x] Estimate reconciliation completed (no source estimate, N/A)
- [x] Summary table accurate (17 tasks, L complexity total)

---

## Notes

1. **Atomic Units**: Each task is completable in < 15 minutes (single turn)
2. **Clear Acceptance Criteria**: All criteria derived from PRD user stories
3. **Dependency Sequence**: Core logic (Phase 1) → Deduplication (Phase 4) → Tests (Phase 5) → Docs (Phase 6); Copilot Detection (Phase 2) → Synthesis (Phase 3) → Tests/Docs
4. **Test Coverage**: 7 tests (6 unit + 1 integration) cover all 4 user stories
5. **Type Distribution**: 10 CODE + 7 TEST + 2 DOCS = 19 total work items
6. **Complexity Distribution**: XS (8), S (6), M (3), L (0), XL (0) → Total L

---

**Recommendation**: Route to critic for validation before implementation.
