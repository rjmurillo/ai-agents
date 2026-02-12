# Quick Examples

Complete examples for common GitHub operations.

---

## Comment Triage (Most Common)

```bash
# Which comments need replies? (MOST COMMON USE CASE)
result=$(python3 scripts/pr/get_pr_review_comments.py --pull-request 50 --only-unaddressed)
total=$(echo "$result" | jq '.TotalComments')
if [ "$total" -gt 0 ]; then
    echo "$total comments need attention"
    echo "$result" | jq -r '.Comments[] | "[\(.LifecycleState)] \(.Author): \(.Body[:50])..."'
fi

# Get unaddressed bot comments only (for AI agent workflows)
python3 scripts/pr/get_pr_review_comments.py --pull-request 50 --only-unaddressed --bot-only

# Get comments with full lifecycle state analysis
result=$(python3 scripts/pr/get_unaddressed_comments.py --pull-request 50)
echo "$result" | jq '.LifecycleStateCounts'   # {"NEW":2,"ACKNOWLEDGED":1,"IN_DISCUSSION":3,"RESOLVED":5}
echo "$result" | jq '.DiscussionSubStateCounts'  # {"WONT_FIX":1,"FIX_DESCRIBED":1,"FIX_COMMITTED":0,"NEEDS_CLARIFICATION":1}
echo "$result" | jq '.DomainCounts'              # {"security":1,"bug":2,"style":5,"general":3}
echo "$result" | jq '.AuthorSummary'             # [{"Author":"cursor[bot]","Count":3},{"Author":"coderabbitai[bot]","Count":2}]

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
python3 scripts/pr/get_unaddressed_comments.py --pull-request 50 --all

# Get comment counts by author
result=$(python3 scripts/pr/get_pr_review_comments.py --pull-request 50)
echo "$result" | jq '.AuthorSummary'

# Get comment counts by domain (security, bug, style)
echo "$result" | jq '.DomainCounts'

# Group by domain for security-first processing
python3 scripts/pr/get_pr_review_comments.py --pull-request 50 --group-by-domain
```

---

## PR Operations

```bash
# List open PRs (default)
python3 scripts/pr/get_pull_requests.py

# List all PRs with custom limit
python3 scripts/pr/get_pull_requests.py --state all --limit 100

# Filter PRs by label and state
python3 scripts/pr/get_pull_requests.py --label "bug,priority:P1" --state open

# Filter PRs by author and base branch
python3 scripts/pr/get_pull_requests.py --author rjmurillo --base main

# Get PR with changed files
python3 scripts/pr/get_pr_context.py --pull-request 50 --include-changed-files

# Check if PR is merged before starting work
python3 scripts/pr/test_pr_merged.py --pull-request 50

# Get CI check status
python3 scripts/pr/get_pr_checks.py --pull-request 50

# Wait for CI checks to complete (timeout 10 minutes)
python3 scripts/pr/get_pr_checks.py --pull-request 50 --wait --timeout-seconds 600

# Get only required checks
python3 scripts/pr/get_pr_checks.py --pull-request 50 --required-only

# Detect Copilot follow-up PRs
python3 scripts/pr/detect_copilot_follow_up_pr.py --pr-number 50
```

---

## Thread Operations

```bash
# Reply to review comment (thread-preserving)
python3 scripts/pr/post_pr_comment_reply.py --pull-request 50 --comment-id 123456 --body "Fixed."

# Resolve all unresolved review threads
python3 scripts/pr/resolve_pr_review_thread.py --pull-request 50 --all

# Reply to review thread by thread ID (GraphQL)
python3 scripts/pr/add_pr_review_thread_reply.py --thread-id "PRRT_kwDOQoWRls5m3L76" --body "Fixed."

# Reply to thread and resolve in one operation
python3 scripts/pr/add_pr_review_thread_reply.py --thread-id "PRRT_kwDOQoWRls5m3L76" --body "Fixed." --resolve

# Check if PR is ready to merge (threads resolved, CI passing)
python3 scripts/pr/test_pr_merge_ready.py --pull-request 50
```

---

## Auto-Merge Operations

```bash
# Enable auto-merge with squash
python3 scripts/pr/set_pr_auto_merge.py --pull-request 50 --enable --merge-method SQUASH

# Disable auto-merge
python3 scripts/pr/set_pr_auto_merge.py --pull-request 50 --disable
```

---

## Issue Operations

```bash
# Create new issue
python3 scripts/issue/new_issue.py --title "Bug: Login fails" --body "Steps..." --labels "bug,P1"

# Create PR with validation
python3 scripts/pr/new_pr.py --title "feat: Add feature" --body "Description"

# Close PR with comment
python3 scripts/pr/close_pr.py --pull-request 50 --comment "Superseded by #51"

# Merge PR with squash
python3 scripts/pr/merge_pr.py --pull-request 50 --strategy squash --delete-branch

# Post idempotent comment (prevents duplicates)
python3 scripts/issue/post_issue_comment.py --issue 123 --body "Analysis..." --marker "AI-TRIAGE"
```

---

## Reaction Operations

```bash
# Add reaction to single comment
python3 scripts/reactions/add_comment_reaction.py --comment-id 12345678 --reaction "eyes"

# Add reactions to multiple comments (batch - 88% faster)
python3 scripts/reactions/add_comment_reaction.py --comment-id 123 456 789 --reaction "eyes"

# Acknowledge all comments on a PR (batch)
ids=$(python3 scripts/pr/get_pr_review_comments.py --pull-request 42 | jq -r '.Comments[].id')
python3 scripts/reactions/add_comment_reaction.py --comment-id $ids --reaction "eyes"
```
