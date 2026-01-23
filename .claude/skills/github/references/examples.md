# Quick Examples

Complete examples for common GitHub operations.

---

## Comment Triage (Most Common)

```powershell
# Which comments need replies? (MOST COMMON USE CASE)
$result = pwsh -NoProfile scripts/pr/Get-PRReviewComments.ps1 -PullRequest 50 -OnlyUnaddressed
if ($result.TotalComments -gt 0) {
    Write-Host "$($result.TotalComments) comments need attention"
    $result.Comments | ForEach-Object { Write-Host "[$($_.LifecycleState)] $($_.Author): $($_.Body.Substring(0, 50))..." }
}

# Get unaddressed bot comments only (for AI agent workflows)
pwsh -NoProfile scripts/pr/Get-PRReviewComments.ps1 -PullRequest 50 -OnlyUnaddressed -BotOnly

# Get comments with full lifecycle state analysis
$result = pwsh -NoProfile scripts/pr/Get-UnaddressedComments.ps1 -PullRequest 50
$result.LifecycleStateCounts      # @{NEW=2; ACKNOWLEDGED=1; IN_DISCUSSION=3; RESOLVED=5}
$result.DiscussionSubStateCounts  # @{WONT_FIX=1; FIX_DESCRIBED=1; FIX_COMMITTED=0; NEEDS_CLARIFICATION=1}
$result.DomainCounts              # @{security=1; bug=2; style=5; general=3}
$result.AuthorSummary             # @{Author="cursor[bot]"; Count=3}, @{Author="coderabbitai[bot]"; Count=2}

# Lifecycle states explained:
#   NEW: 0 eyes, 0 replies, unresolved -> needs acknowledgment + reply
#   ACKNOWLEDGED: >0 eyes, 0 replies, unresolved -> needs reply
#   IN_DISCUSSION: >0 eyes, >0 replies, unresolved -> analyze reply content
#   RESOLVED: thread marked resolved -> no action needed

# IN_DISCUSSION sub-states:
#   WONT_FIX: Reply says "won't fix", "out of scope", "future PR" -> resolve thread
#   FIX_DESCRIBED: Reply describes fix, no commit hash -> add commit reference
#   FIX_COMMITTED: Reply has commit hash -> resolve thread
#   NEEDS_CLARIFICATION: Reply asks questions -> wait for response

# Get all comments including resolved (for audit/reporting)
pwsh -NoProfile scripts/pr/Get-UnaddressedComments.ps1 -PullRequest 50 -OnlyUnaddressed:$false

# Get comment counts by author
$result = pwsh -NoProfile scripts/pr/Get-PRReviewComments.ps1 -PullRequest 50
$result.AuthorSummary

# Get comment counts by domain (security, bug, style)
$result.DomainCounts

# Group by domain for security-first processing
pwsh -NoProfile scripts/pr/Get-PRReviewComments.ps1 -PullRequest 50 -GroupByDomain
```

---

## PR Operations

```powershell
# List open PRs (default)
pwsh -NoProfile scripts/pr/Get-PullRequests.ps1

# List all PRs with custom limit
pwsh -NoProfile scripts/pr/Get-PullRequests.ps1 -State all -Limit 100

# Filter PRs by label and state
pwsh -NoProfile scripts/pr/Get-PullRequests.ps1 -Label "bug,priority:P1" -State open

# Filter PRs by author and base branch
pwsh -NoProfile scripts/pr/Get-PullRequests.ps1 -Author rjmurillo -Base main

# Get PR with changed files
pwsh -NoProfile scripts/pr/Get-PRContext.ps1 -PullRequest 50 -IncludeChangedFiles

# Check if PR is merged before starting work
pwsh -NoProfile scripts/pr/Test-PRMerged.ps1 -PullRequest 50

# Get CI check status
pwsh -NoProfile scripts/pr/Get-PRChecks.ps1 -PullRequest 50

# Wait for CI checks to complete (timeout 10 minutes)
pwsh -NoProfile scripts/pr/Get-PRChecks.ps1 -PullRequest 50 -Wait -TimeoutSeconds 600

# Get only required checks
pwsh -NoProfile scripts/pr/Get-PRChecks.ps1 -PullRequest 50 -RequiredOnly

# Detect Copilot follow-up PRs
pwsh -NoProfile scripts/pr/Detect-CopilotFollowUpPR.ps1 -PRNumber 50
```

---

## Thread Operations

```powershell
# Reply to review comment (thread-preserving)
pwsh -NoProfile scripts/pr/Post-PRCommentReply.ps1 -PullRequest 50 -CommentId 123456 -Body "Fixed."

# Resolve all unresolved review threads
pwsh -NoProfile scripts/pr/Resolve-PRReviewThread.ps1 -PullRequest 50 -All

# Reply to review thread by thread ID (GraphQL)
pwsh -NoProfile scripts/pr/Add-PRReviewThreadReply.ps1 -ThreadId "PRRT_kwDOQoWRls5m3L76" -Body "Fixed."

# Reply to thread and resolve in one operation
pwsh -NoProfile scripts/pr/Add-PRReviewThreadReply.ps1 -ThreadId "PRRT_kwDOQoWRls5m3L76" -Body "Fixed." -Resolve

# Check if PR is ready to merge (threads resolved, CI passing)
pwsh -NoProfile scripts/pr/Test-PRMergeReady.ps1 -PullRequest 50
```

---

## Auto-Merge Operations

```powershell
# Enable auto-merge with squash
pwsh -NoProfile scripts/pr/Set-PRAutoMerge.ps1 -PullRequest 50 -Enable -MergeMethod SQUASH

# Disable auto-merge
pwsh -NoProfile scripts/pr/Set-PRAutoMerge.ps1 -PullRequest 50 -Disable
```

---

## Issue Operations

```powershell
# Create new issue
pwsh -NoProfile scripts/issue/New-Issue.ps1 -Title "Bug: Login fails" -Body "Steps..." -Labels "bug,P1"

# Create PR with validation
pwsh -NoProfile scripts/pr/New-PR.ps1 -Title "feat: Add feature" -Body "Description"

# Close PR with comment
pwsh -NoProfile scripts/pr/Close-PR.ps1 -PullRequest 50 -Comment "Superseded by #51"

# Merge PR with squash
pwsh -NoProfile scripts/pr/Merge-PR.ps1 -PullRequest 50 -Strategy squash -DeleteBranch

# Post idempotent comment (prevents duplicates)
pwsh -NoProfile scripts/issue/Post-IssueComment.ps1 -Issue 123 -Body "Analysis..." -Marker "AI-TRIAGE"
```

---

## Reaction Operations

```powershell
# Add reaction to single comment
pwsh -NoProfile scripts/reactions/Add-CommentReaction.ps1 -CommentId 12345678 -Reaction "eyes"

# Add reactions to multiple comments (batch - 88% faster)
pwsh -NoProfile scripts/reactions/Add-CommentReaction.ps1 -CommentId @(123, 456, 789) -Reaction "eyes"

# Acknowledge all comments on a PR (batch)
$ids = pwsh -NoProfile scripts/pr/Get-PRReviewComments.ps1 -PullRequest 42 | ConvertFrom-Json | ForEach-Object { $_.id }
pwsh -NoProfile scripts/reactions/Add-CommentReaction.ps1 -CommentId $ids -Reaction "eyes"
```
