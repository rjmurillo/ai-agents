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
│   │   ├── Get-PRReviewComments.ps1  # Paginated review + issue comments
│   │   ├── Get-PRReviewers.ps1       # Enumerate unique reviewers
│   │   └── Post-PRCommentReply.ps1   # Thread-preserving replies
│   ├── issue/
│   │   ├── Get-IssueContext.ps1      # Issue metadata
│   │   ├── Set-IssueLabels.ps1       # Apply labels with auto-create
│   │   ├── Set-IssueMilestone.ps1    # Assign milestones
│   │   ├── Post-IssueComment.ps1     # Comments with idempotency
│   │   └── Invoke-CopilotAssignment.ps1  # Context synthesis for Copilot
│   └── reactions/
│       └── Add-CommentReaction.ps1   # Add emoji reactions
├── tests/
│   └── (Pester tests)
├── copilot-synthesis.yml             # Copilot context synthesis config
└── SKILL.md
```

## Quick Reference

### PR Operations

```powershell
# Get PR context with changed files
pwsh -NoProfile scripts/pr/Get-PRContext.ps1 -PullRequest 50 -IncludeChangedFiles

# Get review comments only (handles pagination)
pwsh -NoProfile scripts/pr/Get-PRReviewComments.ps1 -PullRequest 50

# Get review + issue comments (includes AI Quality Gate, CodeRabbit summaries)
pwsh -NoProfile scripts/pr/Get-PRReviewComments.ps1 -PullRequest 50 -IncludeIssueComments

# Enumerate reviewers (prevents single-bot blindness per Skill-PR-001)
pwsh -NoProfile scripts/pr/Get-PRReviewers.ps1 -PullRequest 50 -ExcludeBots

# Reply to review comment (thread-preserving per Skill-PR-004)
pwsh -NoProfile scripts/pr/Post-PRCommentReply.ps1 -PullRequest 50 -CommentId 123456 -Body "Fixed in abc1234."

# Post top-level PR comment
pwsh -NoProfile scripts/pr/Post-PRCommentReply.ps1 -PullRequest 50 -Body "All comments addressed."
```

### Issue Operations

```powershell
# Get issue context
pwsh -NoProfile scripts/issue/Get-IssueContext.ps1 -Issue 123

# Apply labels with auto-creation
pwsh -NoProfile scripts/issue/Set-IssueLabels.ps1 -Issue 123 -Labels @("bug", "needs-review") -Priority "P1"

# Assign milestone
pwsh -NoProfile scripts/issue/Set-IssueMilestone.ps1 -Issue 123 -Milestone "v1.0.0"

# Post comment with idempotency marker
pwsh -NoProfile scripts/issue/Post-IssueComment.ps1 -Issue 123 -BodyFile triage.md -Marker "AI-TRIAGE"
```

### Reactions

```powershell
# Acknowledge review comment with eyes
pwsh -NoProfile scripts/reactions/Add-CommentReaction.ps1 -CommentId 12345678 -Reaction "eyes"

# Add thumbs up to issue comment
pwsh -NoProfile scripts/reactions/Add-CommentReaction.ps1 -CommentId 12345678 -CommentType "issue" -Reaction "+1"
```

### Copilot Assignment

```powershell
# Synthesize context and assign Copilot to issue
pwsh -NoProfile scripts/issue/Invoke-CopilotAssignment.ps1 -IssueNumber 123

# Preview synthesis without posting (WhatIf)
pwsh -NoProfile scripts/issue/Invoke-CopilotAssignment.ps1 -IssueNumber 123 -WhatIf

# Use custom config
pwsh -NoProfile scripts/issue/Invoke-CopilotAssignment.ps1 -IssueNumber 123 -ConfigPath "copilot-synthesis.yml"
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
| `Get-IssueComments` | Fetch all comments for an issue |
| `Update-IssueComment` | Update an existing comment |
| `New-IssueComment` | Create a new issue comment |
| `Get-TrustedSourceComments` | Filter comments by trusted users |
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
pwsh -NoProfile scripts/pr/Get-PRContext.ps1 -PullRequest 50

# Explicit - when running outside repo or for different repo
pwsh -NoProfile scripts/pr/Get-PRContext.ps1 -Owner "octocat" -Repo "hello-world" -PullRequest 50
```

### Idempotency with Markers

Use `-Marker` parameter to prevent duplicate comments:

```powershell
# First call - posts comment with <!-- AI-TRIAGE --> marker
pwsh -NoProfile scripts/issue/Post-IssueComment.ps1 -Issue 123 -Body "Analysis..." -Marker "AI-TRIAGE"

# Second call - detects marker, exits with code 5
pwsh -NoProfile scripts/issue/Post-IssueComment.ps1 -Issue 123 -Body "Analysis..." -Marker "AI-TRIAGE"
```

### Body from File

For multi-line content, use `-BodyFile` to avoid escaping issues:

```powershell
pwsh -NoProfile scripts/pr/Post-PRCommentReply.ps1 -PullRequest 50 -CommentId 123 -BodyFile reply.md
pwsh -NoProfile scripts/issue/Post-IssueComment.ps1 -Issue 123 -BodyFile triage-summary.md
```

### Copilot Directive Placement

**Use issue comments for @copilot directives, not review comments.**

```powershell
# RECOMMENDED - Use issue comment for directives
pwsh scripts/issue/Post-IssueComment.ps1 -Issue 123 -Body "@copilot please refactor the function in src/foo.ps1"

# ANTI-PATTERN - Avoid review comments for directives
pwsh scripts/pr/Post-PRCommentReply.ps1 -PullRequest 50 -CommentId 123 -Body "@copilot please refactor this"
```

**Why**: Review comments should focus on code feedback. Directive comments create noise (PR #249: 41 of 42 comments were @copilot directives). See AGENTS.md "Copilot Directive Best Practices" section.

## API Endpoints Used

| Script | Endpoint |
|--------|----------|
| `Get-PRContext` | `gh pr view --json ...` |
| `Get-PRReviewComments` | `pulls/{pr}/comments` + `issues/{pr}/comments` (with `-IncludeIssueComments`) |
| `Get-PRReviewers` | Multiple: pulls/comments, issues/comments, pr view |
| `Post-PRCommentReply` | `repos/{owner}/{repo}/pulls/{pr}/comments` (with in_reply_to) |
| `Get-IssueContext` | `gh issue view --json ...` |
| `Set-IssueLabels` | `repos/{owner}/{repo}/labels`, `gh issue edit --add-label` |
| `Set-IssueMilestone` | `gh issue edit --milestone` |
| `Post-IssueComment` | `repos/{owner}/{repo}/issues/{issue}/comments` |
| `Add-CommentReaction` | `repos/{owner}/{repo}/pulls/comments/{id}/reactions` or `issues/comments/{id}/reactions` |
| `Invoke-CopilotAssignment` | `repos/{owner}/{repo}/issues/{issue}/comments`, `gh issue edit --add-assignee` |

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
