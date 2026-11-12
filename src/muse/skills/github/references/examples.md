# Quick Examples

Complete examples for common GitHub operations.

---

## Script Path

The GitHub scripts ship inside this skill's `scripts` tree, not at the
repository root. Every example below runs its script through the plugin-root
locator, a one-line subshell that finds the plugin root and hands the script
path and its arguments to `lib/ptk_run.py`. Arguments go inside the locator,
before its closing `; fi`.

---

## Comment Triage (Most Common)

```bash
# Which comments need replies? (MOST COMMON USE CASE)
result=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_review_comments.py --pull-request 50 --only-unaddressed; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) )
total=$(echo "$result" | jq '.TotalComments')
if [ "$total" -gt 0 ]; then
    echo "$total comments need attention"
    echo "$result" | jq -r '.Comments[] | "[\(.LifecycleState)] \(.Author): \(.Body[:50])..."'
fi

# Get unaddressed bot comments only (for AI agent workflows)
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_review_comments.py --pull-request 50 --only-unaddressed --bot-only; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Get comments with full lifecycle state analysis
result=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_unaddressed_comments.py --pull-request 50; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) )
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
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_unaddressed_comments.py --pull-request 50 --no-only-unaddressed; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Get comment counts by author
result=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_review_comments.py --pull-request 50; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) )
echo "$result" | jq '.AuthorSummary'

# Get comment counts by domain (security, bug, style)
echo "$result" | jq '.DomainCounts'

# Group by domain for security-first processing
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_review_comments.py --pull-request 50 --group-by-domain; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
```

---

## PR Operations

```bash
# List open PRs (default)
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pull_requests.py; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# List all PRs with custom limit
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pull_requests.py --state all --limit 100; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Filter PRs by label and state
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pull_requests.py --label "bug,priority:P1" --state open; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Filter PRs by author and base branch
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pull_requests.py --author rjmurillo --base main; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Search PRs by keyword or GitHub search syntax
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pull_requests.py --search "fix auth is:open"; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Get PR with changed files
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_context.py --pull-request 50 --include-changed-files; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Check if PR is merged before starting work
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/test_pr_merged.py --pull-request 50; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Get CI check status
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_checks.py --pull-request 50; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Wait for CI checks to complete (keep the budget at or below 570 seconds: the
# 600 second tool call is killed with no result). Exit 7 means still waiting or incomplete: check
# `ChecksIncomplete` before running it again.
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_checks.py --pull-request 50 --wait --timeout-seconds 540; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Get only required checks
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_checks.py --pull-request 50 --required-only; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Detect Copilot follow-up PRs
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/detect_copilot_followup_pr.py --pr-number 50; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
```

---

## Thread Operations

```bash
# Reply to review comment (thread-preserving)
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/post_pr_comment_reply.py --pull-request 50 --comment-id 123456 --body "Fixed."; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Resolve all unresolved review threads
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/resolve_pr_review_thread.py --pull-request 50 --all; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Reply to review thread by thread ID (GraphQL)
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/add_pr_review_thread_reply.py --pull-request 50 --thread-id "PRRT_kwDOQoWRls5m3L76" --body "Fixed."; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Reply to thread and resolve in one operation
HEAD_SHA=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_context.py --pull-request 50 --output-format json; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) | jq -r '.Data.head_sha')
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/add_pr_review_thread_reply.py --pull-request 50 --thread-id "PRRT_kwDOQoWRls5m3L76" --body "Fixed." --resolve --expected-head-sha "$HEAD_SHA"; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Check if PR is ready to merge (threads resolved, CI passing)
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/test_pr_merge_ready.py --pull-request 50; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
```

---

## Auto-Merge Operations

```bash
# Enable auto-merge with squash
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/set_pr_auto_merge.py --pull-request 50 --enable --merge-method SQUASH; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Disable auto-merge
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/set_pr_auto_merge.py --pull-request 50 --disable; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
```

---

## Issue Operations

```bash
# Create new issue the user asked for
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/issue/new_issue.py --title "Bug: Login fails" --body "Steps..." --labels "bug,P1" --source human; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Create an issue an agent selected (Step 0 evidence required)
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/issue/new_issue.py --title "Bug: Login fails" --body "Steps..." --source agent --blocked-by "Checkout team, blocked on login after deploy 412" --signal "auth 500s at 40/min since run 9981"; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Create an issue and assign a milestone in one call
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/issue/new_issue.py --title "Bug: Login fails" --body "Steps..." --source human --milestone v0.7.0; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# List a milestone's issues (composes with --state/--label/--author/--assignee;
# ignored when --search is set)
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/issue/list_issues.py --milestone v0.7.0 --state all --label bug; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Create PR with validation
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/new_pr.py --title "feat: Add feature" --body "Description"; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Close PR with comment
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/close_pr.py --pull-request 50 --comment "Superseded by #51"; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Reopen a closed PR (fires the reopened event)
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/reopen_pr.py --pull-request 50; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Merge PR with squash
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/merge_pr.py --pull-request 50 --strategy squash --delete-branch; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Post idempotent comment (prevents duplicates)
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/issue/post_issue_comment.py --issue 123 --body "Analysis..." --marker "AI-TRIAGE"; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
```

---

## Reaction Operations

```bash
# Add reaction to single comment
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/reactions/add_comment_reaction.py --comment-id 12345678 --reaction "eyes"; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Add reactions to multiple comments (batch - 88% faster)
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/reactions/add_comment_reaction.py --comment-id 123 456 789 --reaction "eyes"; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Acknowledge all comments on a PR (batch)
ids=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_review_comments.py --pull-request 42; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) | jq -r '.Comments[].id')
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/reactions/add_comment_reaction.py --comment-id $ids --reaction "eyes"; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
```
