# PR Review: Use REST API for Review Comment Replies

## Problem

The GraphQL mutation `AddPullRequestReviewComment` fails with permission error for bot accounts:

```
gh: rjmurillo-bot does not have the correct permissions to execute `AddPullRequestReviewComment`
```

**This is NOT an OAuth scope issue.** Adding `write:discussion` scope does not help. The GraphQL mutation has a different permission model that restricts bot accounts from adding review comments to other users' reviews.

Tested scopes that still fail:
- `repo` (full repository access)
- `write:discussion` (read/write discussions)
- Both combined

## Solution

Use the REST API instead of GraphQL for replying to review comments:

```bash
# REST API works for bot accounts
gh api repos/{owner}/{repo}/pulls/{pull_number}/comments \
  -X POST \
  -f body="Reply message" \
  -F in_reply_to={comment_id}
```

## Why This Works

- REST API `POST /repos/{owner}/{repo}/pulls/{pull_number}/comments` uses `repo` scope
- GraphQL `AddPullRequestReviewComment` may require additional permissions or user context
- Bot accounts (OAuth apps) have different permission models than user accounts

## Pattern for pr-comment-responder Skill

**Use the GitHub skill script** instead of raw API calls:

```powershell
# Use the skill script for thread-preserving replies
pwsh .claude/skills/github/scripts/pr/Post-PRCommentReply.ps1 `
  -PullRequest 465 `
  -CommentId 2649934270 `
  -Body "Addressed in commit abc123"
```

The script (`Post-PRCommentReply.ps1`) uses the REST `/replies` endpoint for proper thread preservation:
- `repos/{owner}/{repo}/pulls/{pr}/comments/{comment_id}/replies`

### Manual REST API (if script unavailable)

```bash
# Get review comment ID
comment_id=$(gh api repos/{owner}/{repo}/pulls/{pr}/comments --jq '.[0].id')

# Reply via REST (uses in_reply_to for thread context)
gh api repos/{owner}/{repo}/pulls/{pr}/comments \
  -X POST \
  -f body="Addressed in commit abc123" \
  -F in_reply_to=$comment_id

# Resolve thread via GraphQL (this still works)
gh api graphql -f query='
mutation {
  resolveReviewThread(input: {threadId: "PRRT_xxx"}) {
    thread { isResolved }
  }
}'
```

## Session Context

- Discovered: Session handling PR #465 review comments
- Bot: rjmurillo-bot
- Token scopes: gist, read:org, repo, workflow
