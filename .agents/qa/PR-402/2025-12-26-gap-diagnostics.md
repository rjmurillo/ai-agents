# PR Maintenance Workflow Gap Diagnostics

**Date**: 2025-12-26
**PR**: #402 - fix(ci): add visibility message when PR maintenance processes 0 PRs
**Branch**: fix/400-pr-maintenance-visibility

## Executive Summary

User feedback identified 6 PRs with incorrect disposition by the PR maintenance workflow. Root cause analysis reveals 3 fundamental gaps in the implementation that cause bot-authored PRs to be wrongly placed in the Blocked list instead of ActionRequired.

---

## Gap 1: Bot-Authored PRs with Conflicts Wrongly Blocked

### Affected PRs
- #365: fix(memory): rename skill- prefix files and add naming validation
- #353: fix(ci): emit WARN for Copilot auth failures instead of CRITICAL_FAIL
- #301: docs: autonomous PR monitoring prompt and retrospective
- #255: feat(github-skill): enhance skill for Claude effectiveness
- #235: feat(github-skills): add issue comments support to Get-PRReviewComments

### Root Cause

**File**: `scripts/Invoke-PRMaintenance.ps1`
**Lines**: 1359-1372

```powershell
if ($pr.mergeable -eq 'CONFLICTING') {
    Write-Log "PR #$($pr.number) has merge conflicts - attempting resolution" -Level ACTION
    $resolved = Resolve-PRConflicts -Owner $Owner -Repo $Repo -PRNumber $pr.number -BranchName $pr.headRefName -TargetBranch $pr.baseRefName
    if ($resolved) {
        $results.ConflictsResolved++
    }
    else {
        # BUG: Adds ALL failed conflict resolutions to Blocked
        # regardless of whether bot is author and has authority
        $null = $results.Blocked.Add(@{
            PR = $pr.number
            Author = $authorLogin
            Reason = 'UNRESOLVABLE_CONFLICTS'
            Title = $pr.title
        })
    }
}
```

### Expected Behavior

When conflict resolution fails for a bot-authored PR:
1. The PR should REMAIN in ActionRequired (not moved to Blocked)
2. Reason should indicate manual conflict resolution needed
3. Action should be `/pr-review` to trigger manual resolution by the bot
4. Bot has FULL AUTHORITY over its own PRs

### Actual Behavior

ALL PRs with failed conflict resolution are added to Blocked, regardless of authorship. This is incorrect because:
- Bot-authored PRs can be manually resolved by the bot via `/pr-review`
- Only non-bot-authored PRs should be blocked (require human intervention)

### Recommended Fix

```powershell
if (-not $resolved) {
    if ($isAgentControlledBot) {
        # Bot can manually resolve - add to ActionRequired instead
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
        # Non-bot PR - requires human intervention
        $null = $results.Blocked.Add(@{
            PR = $pr.number
            Author = $authorLogin
            Reason = 'UNRESOLVABLE_CONFLICTS'
            Title = $pr.title
        })
    }
}
```

---

## Gap 2: Bot-Authored PRs with Unaddressed Comments Not Triggering Action

### Affected PRs
Same as Gap 1, plus unaddressed comment counts:
- #365: 7 unaddressed comments
- #353: 1 unaddressed comment
- #301: 7 unaddressed comments
- #255: 3 unaddressed comments
- #235: 2 unaddressed comments

### Root Cause

**File**: `scripts/Invoke-PRMaintenance.ps1`
**Lines**: 1270-1288

```powershell
if ($isAgentControlledBot -or $isBotReviewer) {
    $role = if ($isAgentControlledBot) { 'author' } else { 'reviewer' }
    if ($hasChangesRequested) {
        # BUG: Only triggers action when reviewDecision == CHANGES_REQUESTED
        # Ignores unaddressed bot comments when reviewDecision is null or APPROVED
        Write-Log "PR #$($pr.number): rjmurillo-bot is $role with CHANGES_REQUESTED -> /pr-review" -Level WARN
        $null = $results.ActionRequired.Add(...)
    } else {
        // BUG: "maintenance only" when there are unaddressed comments
        Write-Log "PR #$($pr.number): rjmurillo-bot is $role, no CHANGES_REQUESTED -> maintenance only" -Level INFO
    }

    // Eyes reaction is added but comments are not PROCESSED
    $unacked = Get-UnacknowledgedComments(...)
    foreach ($comment in $unacked) {
        // Only adds eyes reaction - does NOT add to ActionRequired
        $acked = Add-CommentReaction(...)
    }
}
```

### Expected Behavior

Bot-authored PRs with unaddressed bot comments should:
1. Be added to ActionRequired even without CHANGES_REQUESTED
2. Trigger `/pr-review` to address the comments
3. Comments should be RESPONDED TO, not just acknowledged with eyes

### Actual Behavior

- Eyes reaction is added to comments
- But PR is NOT added to ActionRequired unless reviewDecision == CHANGES_REQUESTED
- Comments remain unaddressed (no replies, no resolution)

### Recommended Fix

```powershell
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
```

---

## Gap 3: Bot as Reviewer on Copilot PR Should Synthesize for @copilot

### Affected PRs
- #247: feat: Implement technical guardrails for autonomous agent execution
  - Author: app/copilot-swe-agent
  - Reviewer: rjmurillo-bot
  - Status: CHANGES_REQUESTED
  - Other bots left feedback: coderabbitai, cursor[bot], gemini-code-assist

### Root Cause

**File**: `scripts/Invoke-PRMaintenance.ps1`
**Lines**: 1270-1288, 1325-1337

When rjmurillo-bot is a REVIEWER on a copilot-swe-agent PR:
1. Script detects `$isBotReviewer = $true`
2. Checks `$hasChangesRequested = $true`
3. Adds to ActionRequired with `/pr-review via pr-comment-responder`

BUT: The `/pr-review` action is designed for rjmurillo-bot as AUTHOR.
For copilot-swe-agent PRs, the correct action is to:
1. Collect feedback from other bots (coderabbitai, cursor[bot])
2. Synthesize into a prompt directed at `@copilot`
3. Post as a new comment to trigger copilot-swe-agent

### Expected Behavior

When rjmurillo-bot is reviewer on copilot-swe-agent PR:
1. Detect copilot-swe-agent authorship
2. Collect unaddressed comments from other bots
3. Generate synthesis prompt: "@copilot Please address the following feedback: [summary]"
4. Post comment to PR
5. Action = 'Synthesize feedback for @copilot' (not '/pr-review')

### Actual Behavior

- PR added to ActionRequired with generic `/pr-review` action
- No synthesis happens
- copilot-swe-agent never receives directed prompt
- PR remains blocked

### Protocol Gap

The protocol document (`.agents/architecture/bot-author-feedback-protocol.md`) does not specify this scenario:
- Line 137-139 shows bot reviewer triggers `/pr-review`
- But this assumes rjmurillo-bot can implement fixes
- For copilot-swe-agent PRs, a different action is needed

### Recommended Fix

1. **Detect copilot-swe-agent authorship**:
```powershell
$isCopilotPR = $botInfo.Category -eq 'mention-triggered' -and $authorLogin -match 'copilot'
```

2. **Synthesize and delegate**:
```powershell
if ($isBotReviewer -and $isCopilotPR) {
    # Collect non-copilot bot feedback
    $otherBotComments = @($comments | Where-Object {
        $_.user.type -eq 'Bot' -and
        $_.user.login -notmatch 'copilot' -and
        $_.body -notmatch '@copilot'
    })

    if ($otherBotComments.Count -gt 0) {
        $null = $results.ActionRequired.Add(@{
            PR = $pr.number
            Author = $authorLogin
            Reason = 'COPILOT_SYNTHESIS_NEEDED'
            Title = $pr.title
            Category = 'synthesis-required'
            Action = 'Synthesize bot feedback and direct to @copilot'
            CommentsToSynthesize = $otherBotComments.Count
        })
    }
}
```

---

## Gap 4: PR Placed in Both ActionRequired AND Blocked

### Affected PRs
- #235: Added to ActionRequired (CHANGES_REQUESTED) AND Blocked (UNRESOLVABLE_CONFLICTS)

### Root Cause

The conflict resolution logic (lines 1359-1372) runs AFTER the ActionRequired logic (lines 1269-1343). When a bot-authored PR:
1. Has CHANGES_REQUESTED -> added to ActionRequired
2. Has CONFLICTING mergeable -> conflict resolution attempted
3. Conflict resolution fails -> ALSO added to Blocked

This results in duplicate entries with conflicting status.

### Expected Behavior

A PR should appear in exactly ONE list:
- ActionRequired: Bot can take action
- Blocked: Requires human intervention

### Recommended Fix

Modify conflict resolution to check if PR is already in ActionRequired:

```powershell
if (-not $resolved) {
    $alreadyInActionRequired = $results.ActionRequired | Where-Object { $_.PR -eq $pr.number }

    if ($alreadyInActionRequired) {
        # Update existing entry with conflict info
        $alreadyInActionRequired.HasConflicts = $true
        $alreadyInActionRequired.Action = "$($alreadyInActionRequired.Action) + resolve conflicts"
    }
    elseif ($isAgentControlledBot) {
        # Add to ActionRequired (not Blocked)
        $null = $results.ActionRequired.Add(...)
    }
    else {
        # Add to Blocked (non-bot PR)
        $null = $results.Blocked.Add(...)
    }
}
```

---

## Summary of Required Changes

| Gap | Severity | Type | Files Affected |
|-----|----------|------|----------------|
| Gap 1: Conflicts wrongly blocked | P0 | IMPL_GAP | Invoke-PRMaintenance.ps1 |
| Gap 2: Unaddressed comments ignored | P0 | IMPL_GAP | Invoke-PRMaintenance.ps1 |
| Gap 3: Copilot synthesis missing | P0 | SPEC_GAP + IMPL_GAP | Protocol + Script |
| Gap 4: Duplicate PR entries | P1 | IMPL_GAP | Invoke-PRMaintenance.ps1 |

## Protocol Updates Required

1. Add scenario for "Bot as reviewer on mention-triggered PR"
2. Add "Copilot Synthesis" action type
3. Define when bot can manually resolve vs requires human

## Test Cases Required

1. Bot-authored PR with unresolvable conflicts -> ActionRequired (not Blocked)
2. Bot-authored PR with unaddressed comments (no CHANGES_REQUESTED) -> ActionRequired
3. Bot reviewer on copilot-swe-agent PR -> Synthesize for @copilot
4. PR should not appear in both ActionRequired and Blocked

---

## Evidence Links

### PR #365
- https://github.com/rjmurillo/ai-agents/pull/365#discussion_r2645670467
- https://github.com/rjmurillo/ai-agents/pull/365#discussion_r2645670469
- https://github.com/rjmurillo/ai-agents/pull/365#discussion_r2645670470
- https://github.com/rjmurillo/ai-agents/pull/365#issuecomment-3689762769
- https://github.com/rjmurillo/ai-agents/pull/365#issuecomment-3689763415
- https://github.com/rjmurillo/ai-agents/pull/365#discussion_r2645674795
- https://github.com/rjmurillo/ai-agents/pull/365#discussion_r2645674799

### PR #353
- https://github.com/rjmurillo/ai-agents/pull/353#issuecomment-3689647382

### PR #301
- https://github.com/rjmurillo/ai-agents/pull/301#issuecomment-3687605750
- https://github.com/rjmurillo/ai-agents/pull/301#issuecomment-3687774325
- https://github.com/rjmurillo/ai-agents/pull/301#issuecomment-3689607700
- https://github.com/rjmurillo/ai-agents/pull/301#issuecomment-3690353599
- https://github.com/rjmurillo/ai-agents/pull/301#discussion_r2646142037
- https://github.com/rjmurillo/ai-agents/pull/301#discussion_r2646146709
- https://github.com/rjmurillo/ai-agents/pull/301#issuecomment-3690363380

### PR #255
- https://github.com/rjmurillo/ai-agents/pull/255#issuecomment-3683965774
- https://github.com/rjmurillo/ai-agents/pull/255#issuecomment-3683968318
- https://github.com/rjmurillo/ai-agents/pull/255#issuecomment-3683973979

### PR #247
- https://github.com/rjmurillo/ai-agents/pull/247#issuecomment-3682596786
- https://github.com/rjmurillo/ai-agents/pull/247#issuecomment-3682599322
- https://github.com/rjmurillo/ai-agents/pull/247#issuecomment-3682600289

### PR #235
- https://github.com/rjmurillo/ai-agents/pull/235#issuecomment-3681483437
- https://github.com/rjmurillo/ai-agents/pull/235#issuecomment-3681487497
