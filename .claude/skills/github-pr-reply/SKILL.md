---
name: github-pr-reply
description: Post replies to GitHub PR review comments. Use when responding to PR review feedback, addressing reviewer suggestions, clarifying implementation decisions, or posting resolution summaries in pull requests.
allowed-tools: Bash(pwsh:*), Bash(gh api:*), Bash(gh pr:*), Read, Write, Grep, Glob
---

# GitHub PR Reply Skill

## Purpose

This skill helps you efficiently respond to GitHub PR review comments by:

- Formatting well-structured replies using templates
- Posting in-thread replies to maintain conversation context
- Posting top-level PR comments for summaries
- Handling the GitHub API complexity automatically

## When to Use

Invoke this skill when you need to:

- Respond to code review feedback
- Acknowledge or address reviewer suggestions
- Clarify implementation decisions
- Post resolution summaries with commit references
- Document changes made in response to comments

## Quick Usage

### Method 1: Using Post-PRCommentReply.ps1 Script

The generic script in `.claude/skills/github-pr-reply/scripts/Post-PRCommentReply.ps1` handles all GitHub API complexity.

```powershell
# Reply to a review comment (inline body)
pwsh .claude/skills/github-pr-reply/scripts/Post-PRCommentReply.ps1 -PullRequest 50 -CommentId 2625540786 -Body "Fixed in abc1234."

# Reply using body from file (preferred for formatted content)
pwsh .claude/skills/github-pr-reply/scripts/Post-PRCommentReply.ps1 -PullRequest 50 -CommentId 2625540786 -BodyFile reply.md

# Post top-level PR comment
pwsh .claude/skills/github-pr-reply/scripts/Post-PRCommentReply.ps1 -PullRequest 50 -Body "All comments addressed."

# Explicit owner/repo (when not in repo directory)
pwsh .claude/skills/github-pr-reply/scripts/Post-PRCommentReply.ps1 -Owner rjmurillo -Repo ai-agents -PullRequest 50 -CommentId 12345 -BodyFile reply.md
```

### Method 2: Direct GitHub API

```bash
# In-thread reply to review comment
gh api repos/{owner}/{repo}/pulls/{pr}/comments -X POST -f body="Fixed in commit abc1234." -F in_reply_to={comment_id}

# Top-level PR comment (issue comment endpoint)
gh api repos/{owner}/{repo}/issues/{pr}/comments -X POST -f body="Summary of changes..."
```

## Workflow Integration

This skill integrates with the `pr-comment-responder` agent workflow:

1. **Context Gathering**: Agent identifies comments needing responses
2. **Reply Drafting**: Write reply to `.agents/pr-comments/PR-{number}/reply-{comment_id}.md`
3. **Reply Posting**: Use this skill to post the reply
4. **Verification**: Confirm reply was posted successfully

### Standard Reply Workflow

```powershell
# 1. Write reply content to file
$replyPath = ".agents/pr-comments/PR-50/reply-2625540786.md"

# 2. Post reply using script
pwsh scripts/Post-PRCommentReply.ps1 `
    -PullRequest 50 `
    -CommentId 2625540786 `
    -BodyFile $replyPath

# 3. Script outputs confirmation with URL
# Success! URL: https://github.com/owner/repo/pull/50#discussion_r12345
```

## Reply Templates

### Bug Fix Acknowledgment

```text
Fixed in {commit_hash}.

{Brief description of the change}

[code block showing before/after with appropriate language]

{Optional: test coverage notes}
```

### Code Explanation

```markdown
This approach was chosen because {rationale}.

The alternative {alternative} was considered but {why_not_chosen}.

{Optional: link to documentation or ADR}
```

### Requesting Clarification

```markdown
@{reviewer} I want to make sure I understand your feedback correctly.

Are you suggesting {interpretation}?

I chose {approach} because {reason}. Would you prefer {alternative}?
```

### Won't Fix (with rationale)

```markdown
Thanks for the suggestion. After analysis, we've decided not to implement this because:

{Rationale - bullet points}

If you disagree, please let me know and I'll reconsider.
```

### Comprehensive Fix Summary

```text
Fixed in {commit_hash}.

{One-line summary of fix}

[code block showing before/after with appropriate language]

**Test coverage added** ({N} new tests):

**Positive Tests**:
- {test_description_1}
- {test_description_2}

**Negative Tests**:
- {test_description_3}

**Edge Cases**:
- {test_description_4}

All tests verify the fix works correctly.
```

## Script Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `-Owner` | string | No* | Repository owner. Inferred from git remote if not provided. |
| `-Repo` | string | No* | Repository name. Inferred from git remote if not provided. |
| `-PullRequest` | int | Yes | PR number |
| `-CommentId` | long | No** | Review comment ID to reply to |
| `-Body` | string | Yes*** | Reply text (inline) |
| `-BodyFile` | string | Yes*** | Path to file containing reply |
| `-CommentType` | string | No | "review" or "issue". Auto-detected. |

\* Inferred from git remote origin if in a git repository
\** Required for review replies, omit for top-level comments
\*** Mutually exclusive - provide one or the other

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Invalid parameters |
| 2 | Body file not found |
| 3 | GitHub API error |
| 4 | gh CLI not found or not authenticated |

## Best Practices

### DO

- Use `BodyFile` for multi-line replies (avoids escaping issues)
- Reference commit hashes when acknowledging fixes
- Use code blocks for before/after comparisons
- Reply in-thread to maintain conversation context
- Acknowledge the reviewer's contribution

### DON'T

- Mention @copilot or @coderabbitai unnecessarily (triggers re-analysis)
- Use `/issues/{number}/comments` to reply to review comments (breaks threading)
- Post empty or "acknowledged" only replies
- Batch multiple unrelated responses into one comment

## Troubleshooting

### "Could not infer repository info"

Run from within the git repository, or provide `-Owner` and `-Repo` explicitly.

### "GitHub API error: Not Found"

Verify:

1. The PR number exists
2. The comment ID is valid and belongs to this PR
3. You have write access to the repository

### "gh CLI not authenticated"

Run `gh auth login` and authenticate with GitHub.

## Related

- **Agent**: `pr-comment-responder` - Full PR review handling workflow
- **Script**: `.claude/skills/github-pr-reply/scripts/Post-PRCommentReply.ps1` - Generic posting script
- **Tests**: `.claude/skills/github-pr-reply/tests/Post-PRCommentReply.Tests.ps1` - Pester tests
- **Docs**: `AGENTS.md` - Agent system documentation

## Examples in This Repository

See `.agents/pr-comments/PR-50/` for real examples:

- `reply-2625540786.md` - Sample reply content
- `comments.md` - Comment tracking map
- `session-summary.md` - Full session documentation
