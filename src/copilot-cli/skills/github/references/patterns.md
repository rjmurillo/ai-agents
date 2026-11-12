# Common Patterns

Reusable patterns for GitHub CLI operations.

---

## Script Path

The GitHub scripts ship inside this skill's `scripts` tree, not at the
repository root. Every example below runs its script through the plugin-root
locator, a one-line subshell that finds the plugin root and hands the script
path and its arguments to `lib/ptk_run.py`. Arguments go inside the locator,
before its closing `; fi`.

---

## Owner/Repo Inference

All scripts auto-infer from `git remote` when `--owner` and `--repo` are omitted.

---

## Idempotency with Markers

Use `--marker` to prevent duplicate comments:

```bash
# First call: posts comment with <!-- AI-TRIAGE --> marker
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/issue/post_issue_comment.py --issue 123 --body "..." --marker "AI-TRIAGE"; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Second call: skips the post and exits with code 0 (already exists)
```

---

## Body from File

For multi-line content, use `--body-file` to avoid escaping issues.

`new_pr.py`, `edit_pr_body.py`, `close_issue.py`, `reopen_issue.py` and
`post_issue_comment.py` read the body file through the strict shared reader.
The path must be under the repo root or a temp directory, and the file must be
yours, with one link, and not a symlink. A group-writable file needs an
owner-only directory above it; otherwise run `chmod 600` on it. The PR scripts
refuse the git dir, and the three issue scripts accept only a linked worktree's
own git dir. The other body-file scripts, such as `new_issue.py`, still accept
any path under the repo root, a temp directory, or the git dir. A session
scratchpad passes. When sessions share one scratch directory, run
`new_pr.py --prepare-body-file` for a unique name, fill the relative path it
prints, and pass that path.

---

## Thread Management Workflow

```bash
# 1. Get unresolved threads and the PR head SHA
HEAD_SHA=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_context.py --pull-request 50 --output-format json; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) | jq -r '.Data.head_sha')
threads=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_review_threads.py --pull-request 50 --unresolved-only; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) )

# 2. Reply to each thread using thread ID and resolve (recommended)
echo "$threads" | jq -r '.threads[].thread_id' | while read -r tid; do
    ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/add_pr_review_thread_reply.py --pull-request 50 --thread-id "$tid" --body "Fixed." --resolve --expected-head-sha "$HEAD_SHA"; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
done

# 3. Or reply using comment ID (REST API) then batch resolve
echo "$threads" | jq -r '.threads[].first_comment_id' | while read -r cid; do
    ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/post_pr_comment_reply.py --pull-request 50 --comment-id "$cid" --body "Fixed."; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
done
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/resolve_pr_review_thread.py --pull-request 50 --all; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# 4. Merge
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/merge_pr.py --pull-request 50 --strategy squash --delete-branch; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
```

---

## Merge Readiness Check

```bash
# Full merge readiness check
ready=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/test_pr_merge_ready.py --pull-request 50; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) )

can_merge=$(echo "$ready" | jq -r '.CanMerge')
if [ "$can_merge" = "true" ]; then
    ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/merge_pr.py --pull-request 50 --strategy squash --delete-branch; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
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
ready=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/test_pr_merge_ready.py --pull-request 50 --ignore-ci; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) )

can_merge=$(echo "$ready" | jq -r '.CanMerge')
if [ "$can_merge" = "true" ]; then
    # Enable auto-merge - PR will merge when CI passes
    ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/set_pr_auto_merge.py --pull-request 50 --enable --merge-method SQUASH; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
    echo "Auto-merge enabled. PR will merge when all checks pass."
else
    echo "Cannot enable auto-merge: $(echo "$ready" | jq -r '.Reasons | join("; ")')"
fi
```

---

## PR Enumeration Workflow

```bash
# Get all open PRs targeting main
prs=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pull_requests.py --state open --base main; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) )

# Check each PR for merge readiness
echo "$prs" | jq -r '.Data.PullRequests[].number' | while read -r pr_num; do
    ready=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/test_pr_merge_ready.py --pull-request "$pr_num"; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) )
    can_merge=$(echo "$ready" | jq -r '.CanMerge')
    if [ "$can_merge" = "true" ]; then
        echo "PR #$pr_num is ready to merge"
        ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/merge_pr.py --pull-request "$pr_num" --strategy squash --delete-branch; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
    fi
done
```

---

## Pre-Review Check

Always check if PR is merged before starting review work:

```bash
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/test_pr_merged.py --pull-request 50; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
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
comments=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_review_comments.py --pull-request 50; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) )
ids=$(echo "$comments" | jq -r '.Comments[].id')

# Batch acknowledge (saves ~1.2s per comment vs. individual calls)
result=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/reactions/add_comment_reaction.py --comment-id $ids --reaction "eyes"; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) )

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
checks=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_checks.py --pull-request 50; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) )

merge_ref_usable=$(echo "$checks" | jq -r '.Data.MergeRefUsable')
all_passing=$(echo "$checks" | jq -r '.Data.AllPassing')
failed_count=$(echo "$checks" | jq '.Data.FailedCount')

if [ "$merge_ref_usable" = "false" ]; then
    echo "BLOCKED: PR merge ref cannot be built, so CI status is incomplete"
elif [ "$all_passing" = "true" ]; then
    echo "All CI checks passing"
elif [ "$failed_count" -gt 0 ]; then
    echo "BLOCKED: $failed_count check(s) failed"
    echo "$checks" | jq -r '.Data.Checks[] | select(.Conclusion != "SUCCESS" and .Conclusion != "NEUTRAL" and .Conclusion != "SKIPPED" and .Conclusion != null) | "  - \(.Name): \(.DetailsUrl)"'
    exit 1
else
    pending=$(echo "$checks" | jq '.Data.PendingCount')
    echo "Pending: $pending check(s) still running"
fi

# Poll until all checks complete (or timeout). Keep --timeout-seconds at or below
# 570: a 600 second tool call is killed with no result.
checks=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_checks.py --pull-request 50 --wait --timeout-seconds 540; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) )

if [ $? -eq 7 ]; then
    echo "Timeout waiting for checks (exit 7 also means ChecksIncomplete: check it before re-running)"
    exit 1
fi

all_passing=$(echo "$checks" | jq -r '.Data.AllPassing')
if [ "$all_passing" = "true" ]; then
    ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/merge_pr.py --pull-request 50 --strategy squash --delete-branch; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
fi
```

---

## Integration Pattern

```bash
# Chain operations with error handling
pr=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_context.py --pull-request 50; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) )
success=$(echo "$pr" | jq -r '.Success')
if [ "$success" != "true" ]; then
    echo "Failed to get PR context" >&2
    exit 1
fi

checks=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_checks.py --pull-request 50 --wait; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) )
all_passing=$(echo "$checks" | jq -r '.Data.AllPassing')
if [ "$all_passing" = "true" ]; then
    ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/merge_pr.py --pull-request 50 --strategy squash; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
fi
```
