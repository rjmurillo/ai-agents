# Session 85: PR Review Workflow Improvements

**Date**: 2025-12-23
**Status**: [IMPLEMENTED]
**Branch**: feat/pr-review-merge-state-verification
**Related Session**: [Session 85](.agents/sessions/2025-12-23-session-85-pr-315-post-merge-analysis.md)

## Objective

Implement lessons learned from Session 85 to prevent wasted effort on already-merged PRs and improve PR review workflow efficiency.

## Background

Session 85 discovered that PR #315 was already merged, but `gh pr view` returned stale "OPEN" status. This led to 15 minutes of unnecessary thread resolution work. Three new skills were identified:

- **Skill-PR-Review-004**: Thread Resolution Protocol
- **Skill-PR-Review-005**: Batch Thread Resolution Efficiency
- **Skill-PR-Review-007**: PR Merge State Verification (prevents this issue)

## Changes Required

### 1. Add PR Merge State Verification to pr-review Command

**File**: `.claude/commands/pr-review.md`

**Location**: Step 1: Parse and Validate PRs

**Current**:
```powershell
pwsh .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest {number}
```

Verify: PR exists, is open (state != MERGED, CLOSED), targets current repo.

**Proposed Addition**:

```markdown
### Step 1: Parse and Validate PRs

For `all-open`, query: `gh pr list --state open --json number,reviewDecision`

For each PR number, validate using:

```powershell
pwsh .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest {number}
```

**CRITICAL - Verify PR Merge State (Skill-PR-Review-007)**:

Before proceeding with review work, verify PR has not been merged via GraphQL (source of truth):

```bash
# Check merge state via GraphQL
merge_state=$(gh api graphql -f query='
query {
  repository(owner: "OWNER", name: "REPO") {
    pullRequest(number: PR_NUMBER) {
      state
      merged
      mergedAt
    }
  }
}' --jq '.data.repository.pullRequest.merged')

if [[ "$merge_state" == "true" ]]; then
  echo "PR #PR_NUMBER is already merged. Skipping review work."
  continue  # Skip to next PR
fi
```

Verify: PR exists, is open (state != MERGED, CLOSED), targets current repo, **NOT already merged**.
```

**Rationale**: `gh pr view --json state` may return stale data for recently merged PRs. GraphQL API is source of truth.

### 2. Update pr-comment-responder Skill Instructions

**File**: User skill at `~/.claude/skills/pr-comment-responder/SKILL.md` (user-managed)

**Location**: Phase 1: Context Gathering, Step 1.2

**Proposed Addition**:

```markdown
### Step 1.2: Verify PR Merge State (BLOCKING)

**CRITICAL - Skill-PR-Review-007**: Before fetching PR metadata, verify PR has not been merged.

```bash
# Check merge state via GraphQL (source of truth)
merge_state=$(gh api graphql -f query='
query {
  repository(owner: "OWNER", name: "REPO") {
    pullRequest(number: PR_NUMBER) {
      state
      merged
      mergedAt
    }
  }
}' --jq '.data.repository.pullRequest')

if [[ "$(echo $merge_state | jq -r '.merged')" == "true" ]]; then
  echo "[SKIP] PR #PR_NUMBER merged at $(echo $merge_state | jq -r '.mergedAt'). No review work needed."
  exit 0
fi
```

**If merged=true**: Skip all remaining phases. Create session log documenting skip reason, then exit.

**Why this matters**: `gh pr view` may return stale "OPEN" for recently merged PRs → wasted effort
```

**Note**: This is documentation guidance for the user skill. User must update their own skill file.

### 3. Document Thread Resolution Protocol

**File**: `.claude/commands/pr-review.md`

**Location**: New section after "Completion Criteria"

**Proposed Addition**:

```markdown
## Thread Resolution Protocol (Skill-PR-Review-004, -005)

### Single Thread Resolution

After replying to a review comment, resolve the thread via GraphQL:

```bash
# Step 1: Reply to comment (via pr-comment-responder skill)
# Step 2: Resolve thread (REQUIRED separate step)
gh api graphql -f query='
mutation($id: ID!) {
  resolveReviewThread(input: {threadId: $id}) {
    thread { isResolved }
  }
}' -f id="PRRT_xxx"
```

**CRITICAL**: Replying to a comment does NOT automatically resolve the thread.

### Batch Thread Resolution (Skill-PR-Review-005)

For 2+ threads, use GraphQL mutation aliases for efficiency:

```bash
gh api graphql -f query='
mutation {
  t1: resolveReviewThread(input: {threadId: "PRRT_xxx"}) { thread { id isResolved } }
  t2: resolveReviewThread(input: {threadId: "PRRT_yyy"}) { thread { id isResolved } }
  t3: resolveReviewThread(input: {threadId: "PRRT_zzz"}) { thread { id isResolved } }
}
'
```

**Benefits**:
- 1 API call instead of N calls
- Reduced network latency (1 round trip vs N)
- Atomic operation (all succeed or all fail)

### Verification

```bash
# Check for unresolved threads
unresolved_count=$(gh api graphql -f query='
query {
  repository(owner: "OWNER", name: "REPO") {
    pullRequest(number: PR_NUMBER) {
      reviewThreads(first: 100) {
        nodes { id isResolved }
      }
    }
  }
}' --jq '.data.repository.pullRequest.reviewThreads.nodes | map(select(.isResolved == false)) | length')

echo "Unresolved threads: $unresolved_count"
```
```

### 4. Create PowerShell Script for PR Merge Verification

**File**: `.claude/skills/github/scripts/pr/Test-PRMerged.ps1` (NEW)

**Purpose**: Reusable script to check PR merge state via GraphQL

**Content**:

```powershell
<#
.SYNOPSIS
    Checks if a GitHub Pull Request has been merged.

.DESCRIPTION
    Queries GitHub GraphQL API to determine PR merge state.
    Use this before starting PR review work to prevent wasted effort on merged PRs.
    Per Skill-PR-Review-007: gh pr view may return stale data.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER PullRequest
    PR number (required).

.EXAMPLE
    .\Test-PRMerged.ps1 -PullRequest 315

.NOTES
    Exit Codes: 0=Not merged, 1=Merged, 2=Error
    Source: Skill-PR-Review-007 (Session 85)
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [int]$PullRequest
)

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

# Use parameterized GraphQL query to prevent injection
$query = @'
query($owner: String!, $repo: String!, $prNumber: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $prNumber) {
      state
      merged
      mergedAt
      mergedBy {
        login
      }
    }
  }
}
'@

Write-Verbose "Querying GraphQL for PR #${PullRequest} merge state"

$result = gh api graphql -f query="$query" -f owner="$Owner" -f repo="$Repo" -F prNumber=$PullRequest 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-ErrorAndExit "GraphQL query failed: $result" 2
}

try {
    $pr = ($result | ConvertFrom-Json).data.repository.pullRequest

    if (-not $pr) {
        Write-ErrorAndExit "PR #$PullRequest not found in $Owner/$Repo. The query might have failed or the PR does not exist." 2
    }
}
catch {
    Write-ErrorAndExit "Failed to parse GraphQL response for PR #$PullRequest. Response: $result. Error: $_" 2
}

$output = [PSCustomObject]@{
    Success      = $true
    PullRequest  = $PullRequest
    Owner        = $Owner
    Repo         = $Repo
    State        = $pr.state
    Merged       = $pr.merged
    MergedAt     = $pr.mergedAt
    MergedBy     = if ($pr.mergedBy) { $pr.mergedBy.login } else { $null }
}

Write-Output $output

if ($pr.merged) {
    $mergedByText = if ($pr.mergedBy) { "@$($pr.mergedBy.login)" } else { "automated process" }
    Write-Host "[MERGED] PR #$PullRequest merged at $($pr.mergedAt) by $mergedByText" -ForegroundColor Yellow
    exit 1  # Exit code 1 = merged (skip review work)
} else {
    Write-Host "[NOT MERGED] PR #$PullRequest is not merged (state: $($pr.state))" -ForegroundColor Green
    exit 0  # Exit code 0 = not merged (safe to proceed)
}
```

### 5. Update Completion Criteria Documentation

**File**: `.claude/commands/pr-review.md`

**Location**: Completion Criteria section, line 171

**Current**:
```markdown
| No unresolved threads | GraphQL query for unresolved reviewThreads | Yes |
```

**Proposed Change**:
```markdown
| No unresolved threads | GraphQL query for unresolved reviewThreads (see Thread Resolution Protocol) | Yes |
| PR not merged | Test-PRMerged.ps1 exit code 0 | Yes |
```

## Implementation Checklist

- [x] Update `.claude/commands/pr-review.md` with merge state verification (Step 1)
- [x] Add Thread Resolution Protocol section to pr-review.md
- [x] Create `.claude/skills/github/scripts/pr/Test-PRMerged.ps1`
- [x] Test `Test-PRMerged.ps1` with merged PR (e.g., PR #315)
- [x] Test `Test-PRMerged.ps1` with open PR
- [ ] Document pr-comment-responder skill update guidance (user-managed skill)
- [x] Update Completion Criteria with PR merge verification
- [ ] Create example scenarios document
- [x] Update session log with implementation results

## Testing Strategy

### Test Case 1: Merged PR Detection

**Scenario**: Run pr-review on already-merged PR #315

**Expected**:
```bash
$ pwsh .claude/skills/github/scripts/pr/Test-PRMerged.ps1 -PullRequest 315
PR #315 merged at 2025-12-23T21:30:00Z by @rjmurillo
Exit code: 1
```

**Result**: pr-review workflow skips PR #315 with message "PR already merged"

### Test Case 2: Open PR Processing

**Scenario**: Run pr-review on open PR with comments

**Expected**:
```bash
$ pwsh .claude/skills/github/scripts/pr/Test-PRMerged.ps1 -PullRequest 320
PR #320 is not merged (state: OPEN)
Exit code: 0
```

**Result**: pr-review workflow proceeds with normal review process

### Test Case 3: Batch Thread Resolution

**Scenario**: Resolve 5+ threads using GraphQL mutation aliases

**Expected**: Single API call resolves all threads atomically

**Verification**:
```bash
unresolved_count=$(gh api graphql ... | jq '... | length')
# Should return 0
```

## Success Criteria

- [ ] All test cases pass
- [ ] Documentation updated in pr-review.md
- [ ] PowerShell script created and tested
- [ ] No breaking changes to existing workflow
- [ ] Session log documents implementation
- [ ] PR created for review

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| GraphQL query timeout | PR review blocked | Add timeout handling, fallback to gh pr view |
| Script dependency on GitHubHelpers | Module not found error | Add import verification |
| Breaking change to pr-comment-responder | User skill breaks | Document as opt-in guidance, not requirement |
| False positive "merged" detection | Skip valid PRs | Verify with multiple fields (state, merged, mergedAt) |

## References

- [Session 85 Log](.agents/sessions/2025-12-23-session-85-pr-315-post-merge-analysis.md)
- [Skill-PR-Review-004, -005, -006](.serena/memories/pr-review-core-workflow.md)
- [PR #315](https://github.com/rjmurillo/ai-agents/pull/315) - Merged PR used for testing
- [PR #320](https://github.com/rjmurillo/ai-agents/pull/320) - Session 85 documentation PR

---

**Status**: [PLANNING] → Ready for implementation
