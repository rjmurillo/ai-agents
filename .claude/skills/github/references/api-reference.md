# GitHub Skill API Reference

Reference documentation for the GitHub skill. For usage, see `../SKILL.md`.

## Exit Codes

| Code | Meaning | Claude Action |
|------|---------|---------------|
| 0 | Success | Parse JSON output |
| 1 | Invalid parameters | Check script parameters |
| 2 | Resource not found | PR/issue/milestone doesn't exist |
| 3 | GitHub API error | Check error message, may be rate limit |
| 4 | gh CLI not authenticated | Run `gh auth login` |
| 5 | Idempotency skip | Comment already exists (expected) |
| 6 | Not mergeable | PR has conflicts or checks failing |

## API Endpoints Used

| Script | Endpoint |
|--------|----------|
| `get_pr_context.py` | `gh pr view --json ...` |
| `get_pr_review_comments.py` | `repos/{owner}/{repo}/pulls/{pr}/comments` |
| `get_pr_review_threads.py` | GraphQL: `repository.pullRequest.reviewThreads` |
| `get_pr_reviewers.py` | Multiple: pulls/comments, issues/comments, pr view |
| `post_pr_comment_reply.py` | `repos/{owner}/{repo}/pulls/{pr}/comments` (with in_reply_to) |
| `resolve_pr_review_thread.py` | GraphQL: `resolveReviewThread` mutation |
| `close_pr.py` | `gh pr close` |
| `merge_pr.py` | `gh pr merge` |
| `Get-IssueContext` | `gh issue view --json ...` |
| `Set-IssueLabels` | `repos/{owner}/{repo}/labels`, `gh issue edit --add-label` |
| `Set-IssueMilestone` | `gh issue edit --milestone` |
| `Post-IssueComment` | `repos/{owner}/{repo}/issues/{issue}/comments` |
| `Add-CommentReaction` | `repos/{owner}/{repo}/pulls/comments/{id}/reactions` or `issues/comments/{id}/reactions` |
| `Invoke-CopilotAssignment` | `repos/{owner}/{repo}/issues/{issue}/comments`, `gh issue edit --add-assignee` |

## Shared Module Functions

All scripts import `modules/GitHubCore.psm1`:

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
| `Test-GitHubNameValid` | Validate owner/repo names (CWE-78 prevention) |
| `Test-SafeFilePath` | Prevent path traversal (CWE-22 prevention) |
| `Assert-ValidBodyFile` | Validate BodyFile parameter |

## Troubleshooting

### "Could not infer repository info"

Run from within a git repository, or provide `-Owner` and `-Repo` explicitly.

### "gh CLI not authenticated"

Run `gh auth login` and authenticate with GitHub.

### Exit code 5

Expected when using `-Marker` and comment already exists. This is idempotency working correctly.

### "Milestone not found"

The milestone must already exist in the repository. Create it via GitHub UI or `gh api`.

### "PR is not mergeable"

Check for merge conflicts or failing required checks. Use `get_pr_context.py` to see `Mergeable` status.

## Skills Applied

| Skill ID | Description | Script |
|----------|-------------|--------|
| Skill-PR-001 | Enumerate all reviewers before triaging | `get_pr_reviewers.py` |
| Skill-PR-004 | Use `in_reply_to` for thread replies | `post_pr_comment_reply.py` |

## Related

- **Agent**: `pr-comment-responder` - Full PR comment handling workflow
- **Workflow**: `.github/workflows/ai-issue-triage.yml` - Uses issue scripts
- **Module**: `.github/scripts/AIReviewCommon.psm1` - Simple wrappers for workflows
- **Memory**: `usage-mandatory` - Enforcement rules for using skills
