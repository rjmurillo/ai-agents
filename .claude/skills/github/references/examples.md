# Quick Examples

Complete examples for common GitHub operations.

---

## Comment Triage (Most Common)

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

# Which comments need replies? (MOST COMMON USE CASE)
result=$(python3 "$SCRIPTS_DIR/pr/get_unaddressed_comments.py" --pull-request 50)
echo "$result" | jq '.TotalComments'

# Get comments with full lifecycle state analysis
python3 "$SCRIPTS_DIR/pr/get_unaddressed_comments.py" --pull-request 50
# Output includes: LifecycleStateCounts, DiscussionSubStateCounts, DomainCounts, AuthorSummary

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
python3 "$SCRIPTS_DIR/pr/get_unaddressed_comments.py" --pull-request 50 --all
```

---

## PR Operations

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

# List open PRs (default)
python3 "$SCRIPTS_DIR/pr/get_pull_requests.py"

# List all PRs with custom limit
python3 "$SCRIPTS_DIR/pr/get_pull_requests.py" --state all --limit 100

# Filter PRs by label and state
python3 "$SCRIPTS_DIR/pr/get_pull_requests.py" --label "bug,priority:P1" --state open

# Filter PRs by author and base branch
python3 "$SCRIPTS_DIR/pr/get_pull_requests.py" --author rjmurillo --base main

# Get PR with changed files
python3 "$SCRIPTS_DIR/pr/get_pr_context.py" --pull-request 50 --include-changed-files

# Check if PR is merged before starting work
python3 "$SCRIPTS_DIR/pr/test_pr_merged.py" --pull-request 50

# Get CI check status
python3 "$SCRIPTS_DIR/pr/get_pr_checks.py" --pull-request 50

# Wait for CI checks to complete (timeout 10 minutes)
python3 "$SCRIPTS_DIR/pr/get_pr_checks.py" --pull-request 50 --wait --timeout-seconds 600

# Get only required checks
python3 "$SCRIPTS_DIR/pr/get_pr_checks.py" --pull-request 50 --required-only

# Detect Copilot follow-up PRs
python3 "$SCRIPTS_DIR/pr/detect_copilot_follow_up_pr.py" --pr-number 50
```

---

## Thread Operations

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

# Reply to review comment (thread-preserving)
python3 "$SCRIPTS_DIR/pr/post_pr_comment_reply.py" --pull-request 50 --comment-id 123456 --body "Fixed."

# Resolve all unresolved review threads
python3 "$SCRIPTS_DIR/pr/resolve_pr_review_thread.py" --pull-request 50 --all

# Reply to review thread by thread ID (GraphQL)
python3 "$SCRIPTS_DIR/pr/add_pr_review_thread_reply.py" --thread-id "PRRT_kwDOQoWRls5m3L76" --body "Fixed."

# Reply to thread and resolve in one operation
python3 "$SCRIPTS_DIR/pr/add_pr_review_thread_reply.py" --thread-id "PRRT_kwDOQoWRls5m3L76" --body "Fixed." --resolve

# Check if PR is ready to merge (threads resolved, CI passing)
python3 "$SCRIPTS_DIR/pr/test_pr_merge_ready.py" --pull-request 50
```

---

## Auto-Merge Operations

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

# Enable auto-merge with squash
python3 "$SCRIPTS_DIR/pr/set_pr_auto_merge.py" --pull-request 50 --enable --merge-method SQUASH

# Disable auto-merge
python3 "$SCRIPTS_DIR/pr/set_pr_auto_merge.py" --pull-request 50 --disable
```

---

## Issue Operations

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

# Create new issue
pwsh -NoProfile scripts/issue/New-Issue.ps1 -Title "Bug: Login fails" -Body "Steps..." -Labels "bug,P1"

# Create PR with validation
python3 "$SCRIPTS_DIR/pr/new_pr.py" --title "feat: Add feature" --body "Description"

# Close PR with comment
python3 "$SCRIPTS_DIR/pr/close_pr.py" --pull-request 50 --comment "Superseded by #51"

# Merge PR with squash
python3 "$SCRIPTS_DIR/pr/merge_pr.py" --pull-request 50 --strategy squash --delete-branch

# Post idempotent comment (prevents duplicates)
pwsh -NoProfile scripts/issue/Post-IssueComment.ps1 -Issue 123 -Body "Analysis..." -Marker "AI-TRIAGE"
```

---

## Reaction Operations

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

# Add reaction to single comment
pwsh -NoProfile "$SCRIPTS_DIR/reactions/Add-CommentReaction.ps1" -CommentId 12345678 -Reaction "eyes"

# Add reactions to multiple comments (batch - 88% faster)
pwsh -NoProfile "$SCRIPTS_DIR/reactions/Add-CommentReaction.ps1" -CommentId @(123, 456, 789) -Reaction "eyes"

# Acknowledge all comments on a PR (batch)
ids=$(python3 "$SCRIPTS_DIR/pr/get_pr_review_comments.py" --pull-request 42 | jq -r '.[].id')
for id in $ids; do
    pwsh -NoProfile "$SCRIPTS_DIR/reactions/Add-CommentReaction.ps1" -CommentId "$id" -Reaction "eyes"
done
```
