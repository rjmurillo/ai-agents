# PR Maintenance Workflow Gap Analysis: Acknowledged vs Resolved

**Date**: 2025-12-26
**PR**: #365 (exemplar), #402 (tracking issue)
**Analyst**: Claude Opus 4.5
**Status**: IDENTIFIED

## Executive Summary

The PR maintenance workflow has a semantic gap: it conflates "acknowledged" (eyes reaction) with "resolved" (conversation thread closed). This causes the script to report "no action needed" for PRs with acknowledged but unresolved bot comments.

**Evidence from PR #365**:

- 5 bot comments (3 gemini-code-assist, 2 Copilot)
- All 5 have `reactions.eyes = 1` (acknowledged)
- All 5 had `isResolved = false` (unresolved threads)
- Script output: "rjmurillo-bot is author, no action needed -> maintenance only"

## Five Whys Analysis

### Why 1: Why did the script say "no action needed" for PR #365?

**Answer**: The `Get-UnacknowledgedComments` function returned 0 comments because all comments had `reactions.eyes = 1`.

**Evidence** (`scripts/Invoke-PRMaintenance.ps1`, lines 469-472):

```powershell
$unacked = @($Comments | Where-Object {
    $_.user.type -eq 'Bot' -and
    $_.reactions.eyes -eq 0
})
```

### Why 2: Why does having eyes reaction mean "no action needed"?

**Answer**: The design assumes eyes reaction indicates the comment has been fully addressed. However, "acknowledged" (I see this) is not the same as "resolved" (I fixed this).

**Design gap**: No verification that conversation threads are actually resolved via the GitHub API.

### Why 3: Why aren't conversation threads being checked?

**Answer**: The script only uses the REST API (`/pulls/{number}/comments`) which returns `reactions.eyes` but not thread resolution status. Thread resolution requires the GraphQL API.

**Evidence**: `Resolve-PRReviewThread.ps1` queries threads correctly (lines 84-104):

```graphql
reviewThreads(first: 100) {
    nodes {
        id
        isResolved
    }
}
```

But this is only used for resolving threads, not for detecting unresolved threads during maintenance.

### Why 4: Why wasn't thread resolution status integrated into the maintenance workflow?

**Answer**: Historical design decision. The workflow was built in phases:

1. Phase 1: Acknowledge comments (eyes reaction)
2. Phase 2: Reply with fix (commit SHA)
3. Phase 3: Resolve threads (added later via `Resolve-PRReviewThread.ps1`)

The detection logic (phase 0) was never updated to check phase 3 completion.

### Why 5: Why does the detection only check Phase 1 completion?

**Answer**: The `Get-UnacknowledgedComments` function was designed as a simple filter before the thread resolution feature existed. Its name accurately describes what it does (finds unacknowledged comments), but the calling code incorrectly uses it to determine if ALL work is complete.

**Root Cause**: Semantic confusion between "unacknowledged" and "unaddressed" (needs reply + resolution).

## Gap Identification

### Gap 1: Missing Resolution Status Check

**Location**: `scripts/Invoke-PRMaintenance.ps1`, line 1401

```powershell
$unacked = Get-UnacknowledgedComments -Owner $Owner -Repo $Repo -PRNumber $pr.number -Comments $comments
$hasUnaddressedComments = $unacked.Count -gt 0
```

**Problem**: `hasUnaddressedComments` is true only if `reactions.eyes = 0`. Comments that are acknowledged but unresolved are not detected.

### Gap 2: No Function to Detect Unresolved Threads

**Location**: Missing function in `scripts/Invoke-PRMaintenance.ps1`

**Need**: A function like `Get-UnresolvedComments` that checks both:

1. `reactions.eyes = 0` (unacknowledged), OR
2. `isResolved = false` (thread still open)

### Gap 3: Protocol Documentation Inconsistency

**Location**: `.agents/architecture/bot-author-feedback-protocol.md`, lines 227-240

**Current definition**:

> Eyes reaction is a social indicator of engagement. Use it ONLY when rjmurillo-bot will take action on the item.

**Missing clarity**: Eyes reaction indicates "acknowledged for processing," not "processing complete."

### Gap 4: pr-comment-responder Completion Criteria

**Location**: `.claude/agents/pr-comment-responder.md`, lines 839-946 (Phase 8)

**Current criteria** (line 934):

| Criterion | Check |
|-----------|-------|
| All comments resolved | `grep -c "Status: [COMPLETE]\|[WONTFIX]"` equals total |
| No unresolved threads | `gh pr view --json reviewThreads` all resolved |

**Gap**: This criterion exists in the agent spec but is not enforced by the maintenance script.

## Semantic Model

```text
Comment Lifecycle States:
========================

[NEW] -> [ACKNOWLEDGED] -> [REPLIED] -> [RESOLVED]
  |           |              |             |
  |           |              |             +-- isResolved = true (GraphQL)
  |           |              +-- Has reply comment (in_reply_to_id chain)
  |           +-- reactions.eyes >= 1
  +-- Initial state (no eyes, no reply, not resolved)

Current Detection:  [NEW] only
Required Detection: [NEW], [ACKNOWLEDGED], [REPLIED] (anything before [RESOLVED])
```

## Proposed Fix

### Option A: Extend Get-UnacknowledgedComments (Minimal Change)

Add thread resolution check to existing function:

```powershell
function Get-UnacknowledgedComments {
    # ... existing params ...
    [switch]$IncludeUnresolved  # New parameter

    # Existing filter: eyes = 0
    $unacked = @($Comments | Where-Object {
        $_.user.type -eq 'Bot' -and
        $_.reactions.eyes -eq 0
    })

    if ($IncludeUnresolved) {
        # GraphQL query for unresolved threads
        $unresolvedThreads = Get-UnresolvedReviewThreads -PR $PRNumber
        $unresolvedCommentIds = $unresolvedThreads |
            ForEach-Object { $_.comments.nodes[0].databaseId }

        # Include comments in unresolved threads even if eyes > 0
        $unresolvedButAcked = @($Comments | Where-Object {
            $_.user.type -eq 'Bot' -and
            $_.reactions.eyes -gt 0 -and
            $unresolvedCommentIds -contains $_.id
        })

        $unacked = @($unacked) + @($unresolvedButAcked)
    }

    return $unacked
}
```

**Impact**: Requires adding `Get-UnresolvedReviewThreads` to `Invoke-PRMaintenance.ps1` or importing from skill.

### Option B: New Function Get-UnaddressedComments (Clean Separation)

Create new function with correct semantics:

```powershell
function Get-UnaddressedComments {
    <#
    .SYNOPSIS
        Gets bot comments that are not fully addressed.
    .DESCRIPTION
        A comment is "unaddressed" if ANY of:
        1. No eyes reaction (not acknowledged)
        2. Thread is not resolved (no fix confirmed)

        This differs from Get-UnacknowledgedComments which only checks (1).
    #>
    [CmdletBinding()]
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$PRNumber,
        [array]$Comments = $null
    )

    # Fetch comments if not provided
    if ($null -eq $Comments) {
        $Comments = Get-PRComments -Owner $Owner -Repo $Repo -PRNumber $PRNumber
    }

    # Get unresolved threads from GraphQL
    $unresolvedThreads = Get-UnresolvedReviewThreads -Owner $Owner -Repo $Repo -PR $PRNumber
    $unresolvedCommentIds = @($unresolvedThreads |
        ForEach-Object { $_.comments.nodes[0].databaseId } |
        Where-Object { $_ })

    # Filter: bot comments that are either unacknowledged OR unresolved
    $unaddressed = @($Comments | Where-Object {
        $_.user.type -eq 'Bot' -and (
            $_.reactions.eyes -eq 0 -or    # Not acknowledged
            $unresolvedCommentIds -contains $_.id  # Thread not resolved
        )
    })

    return $unaddressed
}

function Get-UnresolvedReviewThreads {
    [CmdletBinding()]
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$PR
    )

    $query = @"
query {
    repository(owner: "$Owner", name: "$Repo") {
        pullRequest(number: $PR) {
            reviewThreads(first: 100) {
                nodes {
                    id
                    isResolved
                    comments(first: 1) {
                        nodes { databaseId }
                    }
                }
            }
        }
    }
}
"@

    $result = gh api graphql -f query=$query 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Failed to query threads: $result" -Level WARN
        return @()
    }

    $parsed = $result | ConvertFrom-Json
    $threads = $parsed.data.repository.pullRequest.reviewThreads.nodes
    return @($threads | Where-Object { -not $_.isResolved })
}
```

**Integration point** (`Invoke-PRMaintenance.ps1`, line 1401):

```powershell
# BEFORE
$unacked = Get-UnacknowledgedComments -Owner $Owner -Repo $Repo -PRNumber $pr.number -Comments $comments
$hasUnaddressedComments = $unacked.Count -gt 0

# AFTER
$unaddressed = Get-UnaddressedComments -Owner $Owner -Repo $Repo -PRNumber $pr.number -Comments $comments
$hasUnaddressedComments = $unaddressed.Count -gt 0
```

### Option C: Check Thread Resolution Separately (Additive)

Keep existing logic, add parallel check:

```powershell
# Existing: check unacknowledged
$unacked = Get-UnacknowledgedComments -Owner $Owner -Repo $Repo -PRNumber $pr.number -Comments $comments
$hasUnacknowledgedComments = $unacked.Count -gt 0

# NEW: check unresolved threads
$unresolvedThreads = Get-UnresolvedReviewThreads -Owner $Owner -Repo $Repo -PR $pr.number
$hasUnresolvedThreads = $unresolvedThreads.Count -gt 0

# Combined check
$hasUnaddressedComments = $hasUnacknowledgedComments -or $hasUnresolvedThreads
```

## Recommendation

**Option B** (New Function) is recommended:

1. **Semantic clarity**: Function name accurately describes behavior
2. **Backward compatibility**: Existing `Get-UnacknowledgedComments` unchanged
3. **Testability**: New function can be tested in isolation
4. **Single responsibility**: Each function does one thing well

## Success Criteria for Fix

| # | Criterion | Verification |
|---|-----------|--------------|
| 1 | PR #365 detected as needing action | Script output includes "PR #365" in ActionRequired |
| 2 | Acknowledged but unresolved comments flagged | `Get-UnaddressedComments` returns count > 0 when `eyes > 0` but `isResolved = false` |
| 3 | Fully resolved comments not flagged | `Get-UnaddressedComments` returns count = 0 when all threads resolved |
| 4 | Tests pass for new scenarios | New test cases: (1) acked+unresolved, (2) acked+resolved, (3) unacked+unresolved |
| 5 | Documentation updated | `bot-author-feedback-protocol.md` glossary clarifies acknowledged vs resolved |

## Test Cases Required

```powershell
Describe "Get-UnaddressedComments Function" {
    It "Returns empty when all comments resolved (even if not acked)" {
        # Setup: isResolved = true for all threads
        # Expected: Count = 0
    }

    It "Returns comments that are acknowledged but unresolved" {
        # Setup: eyes = 1, isResolved = false
        # Expected: Count > 0
    }

    It "Returns comments that are unacknowledged regardless of resolution" {
        # Setup: eyes = 0, isResolved = false
        # Expected: Count > 0
    }

    It "Returns union of unacked and acked-but-unresolved" {
        # Setup: Mix of both scenarios
        # Expected: All included
    }

    It "Handles GraphQL API failure gracefully" {
        # Setup: GraphQL returns error
        # Expected: Falls back to unacked-only
    }
}
```

## Files to Modify

| File | Change Type | Description |
|------|-------------|-------------|
| `scripts/Invoke-PRMaintenance.ps1` | ADD | `Get-UnresolvedReviewThreads` function |
| `scripts/Invoke-PRMaintenance.ps1` | ADD | `Get-UnaddressedComments` function |
| `scripts/Invoke-PRMaintenance.ps1` | MODIFY | Line ~1401: Use `Get-UnaddressedComments` |
| `scripts/tests/Invoke-PRMaintenance.Tests.ps1` | ADD | Test cases for new functions |
| `.agents/architecture/bot-author-feedback-protocol.md` | MODIFY | Glossary: clarify acknowledged vs resolved |

## Related Context

- **GitHub API**: Review threads use GraphQL `isResolved` field
- **REST API limitation**: `/pulls/{number}/comments` does not expose resolution status
- **Existing tool**: `.claude/skills/github/scripts/pr/Resolve-PRReviewThread.ps1` demonstrates correct GraphQL pattern
- **Issue #402**: Tracking this visibility gap in PR maintenance workflow

## Appendix: PR #365 Evidence

**Before analysis** (script output):

```text
PR #365: rjmurillo-bot is author, no action needed -> maintenance only
```

**Actual state**:

| Comment ID | Author | Eyes | Resolved |
|------------|--------|------|----------|
| 2645670467 | gemini-code-assist[bot] | 1 | false |
| 2645670469 | gemini-code-assist[bot] | 1 | false |
| 2645670470 | gemini-code-assist[bot] | 1 | false |
| 2645674795 | Copilot | 1 | false |
| 2645674799 | Copilot | 1 | false |

**After manual resolution**:

```json
{
  "TotalUnresolved": 5,
  "Resolved": 5,
  "Failed": 0,
  "Success": true
}
```

This confirms the gap: 5 threads were unresolved despite all having eyes reactions, but the script did not detect this.
