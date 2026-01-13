# Quick Examples

Complete examples for common GitHub operations.

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
