---
name: github
description: GitHub CLI operations for PRs, Issues, Labels, Milestones, Comments, and Reactions. Unified skill with shared helpers for DRY code.
allowed-tools: Bash(pwsh:*), Bash(gh api:*), Bash(gh pr:*), Bash(gh issue:*), Read, Write, Grep, Glob
---

# GitHub Skill

Unified skill for GitHub CLI operations aligned with the GitHub REST API.

## Structure

```text
.claude/skills/github/
├── modules/
│   └── GitHubHelpers.psm1    # Shared helper functions (DRY)
├── scripts/
│   ├── pr/
│   │   ├── Get-PRContext.ps1         # PR metadata, diff, files
│   │   ├── Get-PRReviewComments.ps1  # Paginated review comments
│   │   ├── Get-PRReviewers.ps1       # Enumerate unique reviewers
│   │   └── Post-PRCommentReply.ps1   # Thread-preserving replies
│   ├── issue/
│   │   ├── Get-IssueContext.ps1      # Issue metadata
│   │   ├── Set-IssueLabels.ps1       # Apply labels with auto-create
│   │   ├── Set-IssueMilestone.ps1    # Assign milestones
│   │   └── Post-IssueComment.ps1     # Comments with idempotency
│   └── reactions/
│       └── Add-CommentReaction.ps1   # Add emoji reactions
├── tests/
│   └── (Pester tests)
└── SKILL.md
```

## Quick Reference

### PR Operations

```powershell
# Get PR context with changed files
pwsh scripts/pr/Get-PRContext.ps1 -PullRequest 50 -IncludeChangedFiles

# Get all review comments (handles pagination)
pwsh scripts/pr/Get-PRReviewComments.ps1 -PullRequest 50

# Enumerate reviewers (prevents single-bot blindness per Skill-PR-001)
pwsh scripts/pr/Get-PRReviewers.ps1 -PullRequest 50 -ExcludeBots

# Reply to review comment (thread-preserving per Skill-PR-004)
pwsh scripts/pr/Post-PRCommentReply.ps1 -PullRequest 50 -CommentId 123456 -Body "Fixed in abc1234."

# Post top-level PR comment
pwsh scripts/pr/Post-PRCommentReply.ps1 -PullRequest 50 -Body "All comments addressed."
```

### Issue Operations

```powershell
# Get issue context
pwsh scripts/issue/Get-IssueContext.ps1 -Issue 123

# Apply labels with auto-creation
pwsh scripts/issue/Set-IssueLabels.ps1 -Issue 123 -Labels @("bug", "needs-review") -Priority "P1"

# Assign milestone
pwsh scripts/issue/Set-IssueMilestone.ps1 -Issue 123 -Milestone "v1.0.0"

# Post comment with idempotency marker
pwsh scripts/issue/Post-IssueComment.ps1 -Issue 123 -BodyFile triage.md -Marker "AI-TRIAGE"
```

### Reactions

```powershell
# Acknowledge review comment with eyes
pwsh scripts/reactions/Add-CommentReaction.ps1 -CommentId 12345678 -Reaction "eyes"

# Add thumbs up to issue comment
pwsh scripts/reactions/Add-CommentReaction.ps1 -CommentId 12345678 -CommentType "issue" -Reaction "+1"
```

## Shared Module

All scripts import `modules/GitHubHelpers.psm1` which provides:

| Function | Purpose |
|----------|---------|
| `Get-RepoInfo` | Infer owner/repo from git remote |
| `Resolve-RepoParams` | Resolve or error on owner/repo |
| `Test-GhAuthenticated` | Check gh CLI auth status |
| `Assert-GhAuthenticated` | Exit if not authenticated |
| `Write-ErrorAndExit` | Consistent error handling |
| `Invoke-GhApiPaginated` | Fetch all pages from API |
| `Get-PriorityEmoji` | P0-P3 to emoji mapping |
| `Get-ReactionEmoji` | Reaction type to emoji |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Invalid parameters |
| 2 | Resource not found (PR, issue, milestone, label) |
| 3 | GitHub API error |
| 4 | gh CLI not found or not authenticated |
| 5 | Idempotency skip (marker already exists) |

## Skills Applied

| Skill ID | Description | Script |
|----------|-------------|--------|
| Skill-PR-001 | Enumerate all reviewers before triaging | `Get-PRReviewers.ps1` |
| Skill-PR-004 | Use `in_reply_to` for thread replies | `Post-PRCommentReply.ps1` |

## Common Patterns

### Owner/Repo Inference

All scripts support optional `-Owner` and `-Repo` parameters. If omitted, they infer from `git remote get-url origin`.

```powershell
# From within git repo - auto-infers
pwsh scripts/pr/Get-PRContext.ps1 -PullRequest 50

# Explicit - when running outside repo or for different repo
pwsh scripts/pr/Get-PRContext.ps1 -Owner "octocat" -Repo "hello-world" -PullRequest 50
```

### Idempotency with Markers

Use `-Marker` parameter to prevent duplicate comments:

```powershell
# First call - posts comment with <!-- AI-TRIAGE --> marker
pwsh scripts/issue/Post-IssueComment.ps1 -Issue 123 -Body "Analysis..." -Marker "AI-TRIAGE"

# Second call - detects marker, exits with code 5
pwsh scripts/issue/Post-IssueComment.ps1 -Issue 123 -Body "Analysis..." -Marker "AI-TRIAGE"
```

### Body from File

For multi-line content, use `-BodyFile` to avoid escaping issues:

```powershell
pwsh scripts/pr/Post-PRCommentReply.ps1 -PullRequest 50 -CommentId 123 -BodyFile reply.md
pwsh scripts/issue/Post-IssueComment.ps1 -Issue 123 -BodyFile triage-summary.md
```

## API Endpoints Used

| Script | Endpoint |
|--------|----------|
| `Get-PRContext` | `gh pr view --json ...` |
| `Get-PRReviewComments` | `repos/{owner}/{repo}/pulls/{pr}/comments` |
| `Get-PRReviewers` | Multiple: pulls/comments, issues/comments, pr view |
| `Post-PRCommentReply` | `repos/{owner}/{repo}/pulls/{pr}/comments` (with in_reply_to) |
| `Get-IssueContext` | `gh issue view --json ...` |
| `Set-IssueLabels` | `repos/{owner}/{repo}/labels`, `gh issue edit --add-label` |
| `Set-IssueMilestone` | `gh issue edit --milestone` |
| `Post-IssueComment` | `repos/{owner}/{repo}/issues/{issue}/comments` |
| `Add-CommentReaction` | `repos/{owner}/{repo}/pulls/comments/{id}/reactions` or `issues/comments/{id}/reactions` |

## Troubleshooting

### "Could not infer repository info"

Run from within a git repository, or provide `-Owner` and `-Repo` explicitly.

### "gh CLI not authenticated"

Run `gh auth login` and authenticate with GitHub.

### Exit code 5

Expected when using `-Marker` and comment already exists. This is idempotency working correctly.

### "Milestone not found"

The milestone must already exist in the repository. Create it via GitHub UI or `gh api`.

## Related

- **Agent**: `pr-comment-responder` - Full PR comment handling workflow
- **Workflow**: `.github/workflows/ai-issue-triage.yml` - Uses issue scripts
- **Module**: `.github/scripts/AIReviewCommon.psm1` - Simple wrappers for workflows
