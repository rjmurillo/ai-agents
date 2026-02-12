# Common Patterns

Reusable patterns for GitHub CLI operations.

---

## Owner/Repo Inference

All scripts auto-infer from `git remote` when `--owner` and `--repo` are omitted.

---

## Idempotency with Markers

Use `--marker` to prevent duplicate comments:

```bash
# First call: posts comment with <!-- AI-TRIAGE --> marker
python3 scripts/issue/post_issue_comment.py --issue 123 --body "..." --marker "AI-TRIAGE"

# Second call: exits with code 5 (already exists)
```

---

## Body from File

For multi-line content, use `--body-file` to avoid escaping issues.

---

## Thread Management Workflow

```bash
# 1. Get unresolved threads
threads=$(python3 scripts/pr/get_pr_review_threads.py --pull-request 50 --unresolved-only)

# 2. Reply to each thread using thread ID and resolve (recommended)
echo "$threads" | jq -r '.threads[].thread_id' | while read -r tid; do
    python3 scripts/pr/add_pr_review_thread_reply.py --thread-id "$tid" --body "Fixed." --resolve
done

# 3. Or reply using comment ID (REST API) then batch resolve
echo "$threads" | jq -r '.threads[].first_comment_id' | while read -r cid; do
    python3 scripts/pr/post_pr_comment_reply.py --pull-request 50 --comment-id "$cid" --body "Fixed."
done
python3 scripts/pr/resolve_pr_review_thread.py --pull-request 50 --all

# 4. Merge
python3 scripts/pr/merge_pr.py --pull-request 50 --strategy squash --delete-branch
```

---

## Merge Readiness Check

```bash
# Full merge readiness check
ready=$(python3 scripts/pr/test_pr_merge_ready.py --pull-request 50)

can_merge=$(echo "$ready" | jq -r '.CanMerge')
if [ "$can_merge" = "true" ]; then
    python3 scripts/pr/merge_pr.py --pull-request 50 --strategy squash --delete-branch
else
    echo "Cannot merge. Reasons:"
    echo "$ready" | jq -r '.Reasons[]' | while read -r reason; do
        echo "  - $reason"
    done

    # Check specific blockers
    unresolved=$(echo "$ready" | jq '.UnresolvedThreads')
    if [ "$unresolved" -gt 0 ]; then
        echo "Unresolved threads: $unresolved"
    fi

    ci_passing=$(echo "$ready" | jq -r '.CIPassing')
    if [ "$ci_passing" != "true" ]; then
        echo "Failed checks: $(echo "$ready" | jq -r '.FailedChecks | join(", ")')"
        echo "Pending checks: $(echo "$ready" | jq -r '.PendingChecks | join(", ")')"
    fi
fi
```

---

## Auto-Merge Workflow

```bash
# Check current readiness (threads must be resolved, but CI can be pending)
ready=$(python3 scripts/pr/test_pr_merge_ready.py --pull-request 50 --ignore-ci)

can_merge=$(echo "$ready" | jq -r '.CanMerge')
if [ "$can_merge" = "true" ]; then
    # Enable auto-merge - PR will merge when CI passes
    python3 scripts/pr/set_pr_auto_merge.py --pull-request 50 --enable --merge-method SQUASH
    echo "Auto-merge enabled. PR will merge when all checks pass."
else
    echo "Cannot enable auto-merge: $(echo "$ready" | jq -r '.Reasons | join("; ")')"
fi
```

---

## PR Enumeration Workflow

```bash
# Get all open PRs targeting main
prs=$(python3 scripts/pr/get_pull_requests.py --state open --base main)

# Check each PR for merge readiness
echo "$prs" | jq -r '.[].number' | while read -r pr_num; do
    ready=$(python3 scripts/pr/test_pr_merge_ready.py --pull-request "$pr_num")
    can_merge=$(echo "$ready" | jq -r '.CanMerge')
    if [ "$can_merge" = "true" ]; then
        echo "PR #$pr_num is ready to merge"
        python3 scripts/pr/merge_pr.py --pull-request "$pr_num" --strategy squash --delete-branch
    fi
done
```

---

## Pre-Review Check

Always check if PR is merged before starting review work:

```bash
python3 scripts/pr/test_pr_merged.py --pull-request 50
if [ $? -eq 1 ]; then
    echo "PR already merged, skipping review"
    exit 0
fi
```

---

## Batch Reactions

Use batch mode for 88% faster acknowledgment of multiple comments:

```bash
# Get all review comment IDs
comments=$(python3 scripts/pr/get_pr_review_comments.py --pull-request 50)
ids=$(echo "$comments" | jq -r '.Comments[].id')

# Batch acknowledge (saves ~1.2s per comment vs. individual calls)
result=$(python3 scripts/reactions/add_comment_reaction.py --comment-id $ids --reaction "eyes")

# Check results
succeeded=$(echo "$result" | jq '.Succeeded')
total=$(echo "$result" | jq '.TotalCount')
echo "Acknowledged $succeeded/$total comments"

failed=$(echo "$result" | jq '.Failed')
if [ "$failed" -gt 0 ]; then
    echo "Failed reactions:"
    echo "$result" | jq -r '.Results[] | select(.Success != true) | .CommentId'
fi
```

---

## CI Check Verification

```bash
# Quick check - get current status
checks=$(python3 scripts/pr/get_pr_checks.py --pull-request 50)

all_passing=$(echo "$checks" | jq -r '.AllPassing')
failed_count=$(echo "$checks" | jq '.FailedCount')

if [ "$all_passing" = "true" ]; then
    echo "All CI checks passing"
elif [ "$failed_count" -gt 0 ]; then
    echo "BLOCKED: $failed_count check(s) failed"
    echo "$checks" | jq -r '.Checks[] | select(.Conclusion != "SUCCESS" and .Conclusion != "NEUTRAL" and .Conclusion != "SKIPPED" and .Conclusion != null) | "  - \(.Name): \(.DetailsUrl)"'
    exit 1
else
    pending=$(echo "$checks" | jq '.PendingCount')
    echo "Pending: $pending check(s) still running"
fi

# Poll until all checks complete (or timeout)
checks=$(python3 scripts/pr/get_pr_checks.py --pull-request 50 --wait --timeout-seconds 600)

if [ $? -eq 7 ]; then
    echo "Timeout waiting for checks"
    exit 1
fi

all_passing=$(echo "$checks" | jq -r '.AllPassing')
if [ "$all_passing" = "true" ]; then
    python3 scripts/pr/merge_pr.py --pull-request 50 --strategy squash --delete-branch
fi
```

---

## Integration Pattern

```bash
# Chain operations with error handling
pr=$(python3 scripts/pr/get_pr_context.py --pull-request 50)
success=$(echo "$pr" | jq -r '.Success')
if [ "$success" != "true" ]; then
    echo "Failed to get PR context" >&2
    exit 1
fi

checks=$(python3 scripts/pr/get_pr_checks.py --pull-request 50 --wait)
all_passing=$(echo "$checks" | jq -r '.AllPassing')
if [ "$all_passing" = "true" ]; then
    python3 scripts/pr/merge_pr.py --pull-request 50 --strategy squash
fi
```
