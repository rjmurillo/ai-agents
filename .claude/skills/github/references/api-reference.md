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
| `get_issue_context.py` | `gh issue view --json ...` |
| `set_issue_labels.py` | `repos/{owner}/{repo}/labels`, `gh issue edit --add-label` |
| `set_issue_milestone.py` | `gh issue edit --milestone` |
| `post_issue_comment.py` | `repos/{owner}/{repo}/issues/{issue}/comments` |
| `add_comment_reaction.py` | `repos/{owner}/{repo}/pulls/comments/{id}/reactions` or `issues/comments/{id}/reactions` |
| `invoke_copilot_assignment.py` | `repos/{owner}/{repo}/issues/{issue}/comments`, `gh issue edit --add-assignee` |

## Shared Library Functions

All scripts use `github_core` Python package (`.claude/lib/github_core/`):

| Function | Purpose |
|----------|---------|
| `get_repo_info()` | Infer owner/repo from git remote |
| `resolve_repo_params()` | Resolve or error on owner/repo |
| `check_gh_authenticated()` | Check gh CLI auth status |
| `assert_gh_authenticated()` | Exit if not authenticated |
| `gh_api_paginated()` | Fetch all pages from API |
| `get_issue_comments()` | Fetch all comments for an issue |
| `update_issue_comment()` | Update an existing comment |
| `new_issue_comment()` | Create a new issue comment |
| `validate_github_name()` | Validate owner/repo names (CWE-78 prevention) |
| `validate_safe_file_path()` | Prevent path traversal (CWE-22 prevention) |

## Troubleshooting

### "Could not infer repository info"

Run from within a git repository, or provide `--owner` and `--repo` explicitly.

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
- **Library**: `.claude/lib/github_core/` - Shared Python helper functions
- **Memory**: `usage-mandatory` - Enforcement rules for using skills
