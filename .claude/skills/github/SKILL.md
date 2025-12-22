---
name: github
description: |
  GitHub CLI operations for PRs, Issues, Labels, Milestones, Comments, and Reactions.
  Use when Claude needs to: (1) Get PR context, diff, or changed files, (2) Reply to
  PR review comments preserving threads, (3) Post idempotent issue comments, (4) Apply
  or create labels, (5) Assign milestones, (6) Add reactions to comments, (7) Close or
  merge PRs, (8) Resolve review threads, (9) Synthesize context for Copilot assignment.
allowed-tools: Bash(pwsh:*), Bash(gh api:*), Bash(gh pr:*), Bash(gh issue:*), Read, Write, Grep, Glob
---

# GitHub Skill

Use these scripts instead of raw `gh` commands for consistent error handling and structured output.

## Decision Tree

```text
Need GitHub data?
├─ PR info/diff → Get-PRContext.ps1
├─ Review comments → Get-PRReviewComments.ps1
├─ Review threads → Get-PRReviewThreads.ps1
├─ Unique reviewers → Get-PRReviewers.ps1
├─ Issue info → Get-IssueContext.ps1
└─ Need to take action?
   ├─ Reply to review → Post-PRCommentReply.ps1
   ├─ Comment on issue → Post-IssueComment.ps1
   ├─ Add reaction → Add-CommentReaction.ps1
   ├─ Apply labels → Set-IssueLabels.ps1
   ├─ Set milestone → Set-IssueMilestone.ps1
   ├─ Resolve threads → Resolve-PRReviewThread.ps1
   ├─ Close PR → Close-PR.ps1
   └─ Merge PR → Merge-PR.ps1
```

## Script Reference

### PR Operations (`scripts/pr/`)

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `Get-PRContext.ps1` | PR metadata, diff, files | `-PullRequest`, `-IncludeChangedFiles`, `-IncludeDiff` |
| `Get-PRReviewComments.ps1` | Paginated review comments | `-PullRequest` |
| `Get-PRReviewThreads.ps1` | Thread-level review data | `-PullRequest`, `-UnresolvedOnly` |
| `Get-PRReviewers.ps1` | Enumerate unique reviewers | `-PullRequest`, `-ExcludeBots` |
| `Post-PRCommentReply.ps1` | Thread-preserving replies | `-PullRequest`, `-CommentId`, `-Body` |
| `Resolve-PRReviewThread.ps1` | Mark threads resolved | `-ThreadId` or `-PullRequest -All` |
| `Close-PR.ps1` | Close PR with comment | `-PullRequest`, `-Comment` |
| `Merge-PR.ps1` | Merge with strategy | `-PullRequest`, `-Strategy`, `-DeleteBranch`, `-Auto` |

### Issue Operations (`scripts/issue/`)

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `Get-IssueContext.ps1` | Issue metadata | `-Issue` |
| `Set-IssueLabels.ps1` | Apply labels (auto-create) | `-Issue`, `-Labels`, `-Priority` |
| `Set-IssueMilestone.ps1` | Assign milestone | `-Issue`, `-Milestone` |
| `Post-IssueComment.ps1` | Comments with idempotency | `-Issue`, `-Body`, `-Marker` |
| `Invoke-CopilotAssignment.ps1` | Synthesize context for Copilot | `-IssueNumber`, `-WhatIf` |

### Reactions (`scripts/reactions/`)

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `Add-CommentReaction.ps1` | Add emoji reactions | `-CommentId`, `-Reaction`, `-CommentType` |

## Quick Examples

```powershell
# Get PR with changed files
pwsh scripts/pr/Get-PRContext.ps1 -PullRequest 50 -IncludeChangedFiles

# Reply to review comment (thread-preserving)
pwsh scripts/pr/Post-PRCommentReply.ps1 -PullRequest 50 -CommentId 123456 -Body "Fixed."

# Resolve all unresolved review threads
pwsh scripts/pr/Resolve-PRReviewThread.ps1 -PullRequest 50 -All

# Close PR with comment
pwsh scripts/pr/Close-PR.ps1 -PullRequest 50 -Comment "Superseded by #51"

# Merge PR with squash
pwsh scripts/pr/Merge-PR.ps1 -PullRequest 50 -Strategy squash -DeleteBranch

# Post idempotent comment (prevents duplicates)
pwsh scripts/issue/Post-IssueComment.ps1 -Issue 123 -Body "Analysis..." -Marker "AI-TRIAGE"

# Add reaction
pwsh scripts/reactions/Add-CommentReaction.ps1 -CommentId 12345678 -Reaction "eyes"
```

## Common Patterns

### Owner/Repo Inference

All scripts auto-infer from `git remote` when `-Owner` and `-Repo` are omitted.

### Idempotency with Markers

Use `-Marker` to prevent duplicate comments:

```powershell
# First call - posts comment with <!-- AI-TRIAGE --> marker
pwsh scripts/issue/Post-IssueComment.ps1 -Issue 123 -Body "..." -Marker "AI-TRIAGE"

# Second call - exits with code 5 (already exists)
```

### Body from File

For multi-line content, use `-BodyFile` to avoid escaping issues.

### Thread Management Workflow

```powershell
# 1. Get unresolved threads
$threads = pwsh scripts/pr/Get-PRReviewThreads.ps1 -PullRequest 50 -UnresolvedOnly | ConvertFrom-Json

# 2. Reply to each thread
foreach ($t in $threads.Threads) {
    pwsh scripts/pr/Post-PRCommentReply.ps1 -PullRequest 50 -CommentId $t.FirstCommentId -Body "Fixed."
}

# 3. Resolve all threads
pwsh scripts/pr/Resolve-PRReviewThread.ps1 -PullRequest 50 -All

# 4. Merge
pwsh scripts/pr/Merge-PR.ps1 -PullRequest 50 -Strategy squash -DeleteBranch
```

## Output Format

All scripts output structured JSON with `Success` boolean:

```powershell
$result = pwsh scripts/pr/Get-PRContext.ps1 -PullRequest 50 | ConvertFrom-Json
if ($result.Success) { ... }
```

## See Also

- `references/api-reference.md` - Exit codes, API endpoints, troubleshooting
- `references/copilot-synthesis-guide.md` - Copilot context synthesis documentation
- `modules/GitHubHelpers.psm1` - Shared helper functions
