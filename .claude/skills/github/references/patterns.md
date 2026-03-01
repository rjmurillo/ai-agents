# Common Patterns

Reusable patterns for GitHub CLI operations.

---

## Owner/Repo Inference

All scripts auto-infer from `git remote` when `-Owner` and `-Repo` are omitted.

---

## Idempotency with Markers

Use `-Marker` to prevent duplicate comments:

```powershell
# First call: posts comment with <!-- AI-TRIAGE --> marker
pwsh -NoProfile scripts/issue/Post-IssueComment.ps1 -Issue 123 -Body "..." -Marker "AI-TRIAGE"

# Second call: exits with code 5 (already exists)
```

---

## Body from File

For multi-line content, use `-BodyFile` to avoid escaping issues.

---

## Thread Management Workflow

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

# 1. Get unresolved threads
threads=$(python3 "$SCRIPTS_DIR/pr/get_pr_review_threads.py" --pull-request 50 --unresolved-only)

# 2. Reply to each thread using thread ID (recommended, combines reply + resolve)
for thread_id in $(echo "$threads" | jq -r '.Threads[].ThreadId'); do
    python3 "$SCRIPTS_DIR/pr/add_pr_review_thread_reply.py" --thread-id "$thread_id" --body "Fixed." --resolve
done

# 3. Or reply using comment ID (REST API), then batch resolve
for comment_id in $(echo "$threads" | jq -r '.Threads[].FirstCommentId'); do
    python3 "$SCRIPTS_DIR/pr/post_pr_comment_reply.py" --pull-request 50 --comment-id "$comment_id" --body "Fixed."
done
python3 "$SCRIPTS_DIR/pr/resolve_pr_review_thread.py" --pull-request 50 --all

# 4. Merge
python3 "$SCRIPTS_DIR/pr/merge_pr.py" --pull-request 50 --strategy squash --delete-branch
```

---

## Merge Readiness Check

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

# Full merge readiness check
ready=$(python3 "$SCRIPTS_DIR/pr/test_pr_merge_ready.py" --pull-request 50)

can_merge=$(echo "$ready" | jq -r '.CanMerge')
if [ "$can_merge" = "true" ]; then
    python3 "$SCRIPTS_DIR/pr/merge_pr.py" --pull-request 50 --strategy squash --delete-branch
else
    echo "Cannot merge. Reasons:"
    echo "$ready" | jq -r '.Reasons[]' | while read -r reason; do echo "  - $reason"; done

    # Check specific blockers
    unresolved=$(echo "$ready" | jq -r '.UnresolvedThreads')
    if [ "$unresolved" -gt 0 ]; then
        echo "Unresolved threads: $unresolved"
    fi

    ci_passing=$(echo "$ready" | jq -r '.CIPassing')
    if [ "$ci_passing" = "false" ]; then
        echo "Failed checks: $(echo "$ready" | jq -r '.FailedChecks | join(", ")')"
        echo "Pending checks: $(echo "$ready" | jq -r '.PendingChecks | join(", ")')"
    fi
fi
```

---

## Auto-Merge Workflow

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

# Check current readiness (ignore CI since auto-merge waits for it)
ready=$(python3 "$SCRIPTS_DIR/pr/test_pr_merge_ready.py" --pull-request 50 --ignore-ci)

can_merge=$(echo "$ready" | jq -r '.CanMerge')
if [ "$can_merge" = "true" ]; then
    # Enable auto-merge - PR will merge when CI passes
    python3 "$SCRIPTS_DIR/pr/set_pr_auto_merge.py" --pull-request 50 --enable --merge-method SQUASH
    echo "Auto-merge enabled. PR will merge when all checks pass."
else
    echo "Cannot enable auto-merge: $(echo "$ready" | jq -r '.Reasons | join("; ")')"
fi
```

---

## PR Enumeration Workflow

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

# Get all open PRs targeting main
prs=$(python3 "$SCRIPTS_DIR/pr/get_pull_requests.py" --state open --base main)

# Check each PR for merge readiness
for pr_number in $(echo "$prs" | jq -r '.[].number'); do
    ready=$(python3 "$SCRIPTS_DIR/pr/test_pr_merge_ready.py" --pull-request "$pr_number")
    can_merge=$(echo "$ready" | jq -r '.CanMerge')
    if [ "$can_merge" = "true" ]; then
        echo "PR #$pr_number is ready to merge"
        python3 "$SCRIPTS_DIR/pr/merge_pr.py" --pull-request "$pr_number" --strategy squash --delete-branch
    fi
done
```

---

## Pre-Review Check

Always check if PR is merged before starting review work:

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

python3 "$SCRIPTS_DIR/pr/test_pr_merged.py" --pull-request 50
if [ $? -eq 1 ]; then
    echo "PR already merged, skipping review"
    exit 0
fi
```

---

## Batch Reactions

Use batch mode for 88% faster acknowledgment of multiple comments:

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

# Get all review comment IDs
comments=$(python3 "$SCRIPTS_DIR/pr/get_pr_review_comments.py" --pull-request 50)
ids=$(echo "$comments" | jq -r '.[].id')

# Batch acknowledge (saves ~1.2s per comment vs. individual calls)
for id in $ids; do
    pwsh -NoProfile "$SCRIPTS_DIR/reactions/Add-CommentReaction.ps1" -CommentId "$id" -Reaction "eyes"
done

# Or use batch mode with array
id_array=$(echo "$comments" | jq -r '[.[].id] | join(",")')
result=$(pwsh -NoProfile "$SCRIPTS_DIR/reactions/Add-CommentReaction.ps1" -CommentId "$id_array" -Reaction "eyes")

# Check results
echo "$result" | jq '"Acknowledged \(.Succeeded)/\(.TotalCount) comments"'
```

---

## CI Check Verification

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

# Quick check - get current status
checks=$(python3 "$SCRIPTS_DIR/pr/get_pr_checks.py" --pull-request 50)

all_passing=$(echo "$checks" | jq -r '.AllPassing')
failed_count=$(echo "$checks" | jq -r '.FailedCount')
pending_count=$(echo "$checks" | jq -r '.PendingCount')

if [ "$all_passing" = "true" ]; then
    echo "All CI checks passing"
elif [ "$failed_count" -gt 0 ]; then
    echo "BLOCKED: ${failed_count} check(s) failed"
    echo "$checks" | jq -r '.Checks[] | select(.Conclusion != "SUCCESS" and .Conclusion != "NEUTRAL" and .Conclusion != "SKIPPED" and .Conclusion != null) | "  - \(.Name): \(.DetailsUrl)"'
    exit 1
else
    echo "Pending: ${pending_count} check(s) still running"
fi

# Poll until all checks complete (or timeout)
checks=$(python3 "$SCRIPTS_DIR/pr/get_pr_checks.py" --pull-request 50 --wait --timeout-seconds 600)
exit_code=$?

if [ "$exit_code" -eq 7 ]; then
    echo "Timeout waiting for checks"
    exit 1
fi

all_passing=$(echo "$checks" | jq -r '.AllPassing')
if [ "$all_passing" = "true" ]; then
    python3 "$SCRIPTS_DIR/pr/merge_pr.py" --pull-request 50 --strategy squash --delete-branch
fi
```

---

## Integration Pattern

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

# Chain operations with error handling
pr=$(python3 "$SCRIPTS_DIR/pr/get_pr_context.py" --pull-request 50)
success=$(echo "$pr" | jq -r '.Success')
if [ "$success" != "true" ]; then
    echo "Failed to get PR context" >&2
    exit 1
fi

checks=$(python3 "$SCRIPTS_DIR/pr/get_pr_checks.py" --pull-request 50 --wait)
all_passing=$(echo "$checks" | jq -r '.AllPassing')
if [ "$all_passing" = "true" ]; then
    python3 "$SCRIPTS_DIR/pr/merge_pr.py" --pull-request 50 --strategy squash
fi
```
