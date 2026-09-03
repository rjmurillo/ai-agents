# Transport Routing

Which GitHub transport works is a property of the environment, not of the
operation. Decide it once per session with the preflight, then stop
re-deciding it per call.

```bash
# CLAUDE_PLUGIN_ROOT is set in a vendored install; falls back to .claude in-repo.
SCRIPTS_DIR="${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts/utils"
python3 "$SCRIPTS_DIR/check_github_transport.py"
```

| Verdict | Meaning | What to do |
|---------|---------|------------|
| `Transport: gh` | `gh` holds a working credential | Use the scripts in this skill. Nothing changes. |
| `Transport: gh_unusable` | `gh` cannot reach GitHub for this whole session | Use the GitHub MCP operations below, after checking they are exposed. |
| exit 3 | Quota refusal or transport wobble | Not a transport problem. Wait and retry on `gh`. |
| exit 4 | Credential fault the operator can fix | Not a transport problem. Fix the token. |

The verdict is named `gh_unusable`, not `mcp`, on purpose: the preflight can
only observe `gh`. It cannot see whether a GitHub MCP server is configured, nor
whether the operations you need are among the tools it exposes. A read-only
toolset still leaves a PR workflow unable to reply, resolve, or merge. Confirm
the operations you need exist before relying on them, and report anything
missing as unavailable.

## Operation names differ by harness

The table below names bare MCP operations. Prefix them for your harness:

| Harness | Spelling |
|---------|----------|
| Claude Code | `mcp__github__pull_request_read` |
| Copilot CLI | `github/pull_request_read` |

## Why gh can be installed and still unusable

An agent sandbox that proxies egress (Claude Code on the web, for example)
leaves `gh` on PATH and a token set, then refuses GitHub for the session:

```text
gh: GitHub access is not enabled for this session. An org admin must connect
the Claude GitHub App for this organization. (HTTP 403)
```

`gh auth login` cannot clear this and neither can retrying, because the
credential is not what is being refused. The preflight reports this condition
as the auth status `transport_blocked`.

A narrower refusal exists and does not mean the same thing. A body that says
one GraphQL query is not served, while REST still is, refuses an operation
rather than the session, and it names REST as the way through.

The two bodies therefore take different evidence, which is what the classifier
implements. The account-level REST wording closes the session on its own and is
enough by itself. The narrower GraphQL wording is not: it is promoted only
after both transports have failed, or after a credential probe shows the token
is fine and the refusal is policy. Read "both transports" as the rule for the
narrow body alone (ADR-100, "Two different 403s").

`gh` stays the default everywhere it works, notably CI, where Actions supplies
a working token. Nothing here removes `gh` from those environments.

## Script to MCP operation

Read operations:

| Instead of | Use | Notes |
|------------|-----|-------|
| `get_pr_context.py` | **Composite.** `pull_request_read` method `get`, plus `get_reviews`, `get_check_runs`, and `get_review_comments` | The script returns reviews, the check rollup, and review-thread counts alongside the PR fields. A bare `get` omits all three, so a blocking review or check disappears and the caller reads clean. Gather all four and derive. |
| `get_pr_context.py --include-diff` | `pull_request_read` method `get_diff`, plus the reads above | `--include-diff` adds the diff, it does not replace the rest of the context. |
| `get_pull_requests.py` | `list_pull_requests`, or `search_pull_requests` for filters | |
| `get_pr_checks.py` | **Partial.** `pull_request_read` method `get_check_runs`, paginated to the end, plus `get` for merge state. The required-context half has no MCP operation at all. | The script deduplicates runs, evaluates required and missing contexts, accounts for merge state, and polls. Three things have to be reproduced by hand. **Paginate**: the operation returns at most 100 runs per page and a busy PR exceeds that (this PR reached 139), so a single page silently drops checks. **Keep the latest run per context name**: repeated pushes leave superseded runs in the list, so an obsolete failure reads as current. **Do neither and the verdict is wrong in both directions**, missing a live failure and inventing a dead one. The fourth part is not reproducible at all: no exposed operation reads a branch ruleset or branch protection, so a required context that never emitted a check is invisible, which is exactly when a run list reads clean on a PR that cannot merge. Report checks and merge state, say the required-context set was not read, and never emit a PASS from this pair. For one run's output text, `get_check_run` where the harness exposes it, otherwise `get_job_logs`. |
| `get_pr_check_logs.py` | **Composite.** `pull_request_read` method `get_check_runs`, paginated and reduced as above, then `get_job_logs` per failed run | Not a direct swap: the script takes a PR number and finds the failed run and job IDs itself, while `get_job_logs` requires an ID it cannot discover. Read the check runs first, apply the same pagination and latest-per-context reduction, derive each failed run or job ID, then fetch. Skipping the reduction fetches logs for a superseded run and reports a failure the current head does not have. `failed_only` skips green jobs within one run; it does not replace the discovery step. |
| `get_pr_review_comments.py` | `pull_request_read` method `get_review_comments` | Returns threads with `isResolved` |
| `get_pr_reviews.py` | `pull_request_read` method `get_reviews` | |
| `get_pr_reviewers.py` | union of `get_reviews`, `get_review_comments`, `get_comments`, and `get` | No single-call equivalent. All four are required: the script counts submitted reviews, review-thread authors, PR issue-comment authors, and requested reviewers. Dropping the last two loses reviewers who have not commented, which is the single-bot-blindness case the script exists to catch. |
| `test_pr_merged.py` | `pull_request_read` method `get`, read `merged` | |
| `get_issue_context.py` | `issue_read` method `get` | |
| `get_issue_comments.py` | `issue_read` method `get_comments` | |

Write operations:

| Instead of | Use | Notes |
|------------|-----|-------|
| `new_pr.py` | `create_pull_request` | |
| `edit_pr_body.py` | `update_pull_request` | |
| `post_pr_comment_reply.py` | `add_reply_to_pull_request_comment` with a review-comment id, or `add_issue_comment` when replying at PR top level | The script posts a top-level PR comment when `--comment-id` is omitted. Collapsing both onto the reply tool sends a top-level reply to a comment id it does not have. |
| `add_pr_review_thread_reply.py` | `add_reply_to_pull_request_comment`, after resolving the thread to its root comment id | The script takes a GraphQL thread id, checks the thread belongs to the PR and is not already resolved, and can resolve after replying. The MCP tool takes a review-comment id and performs none of those guards, so look the thread up through `pull_request_read` method `get_review_comments`, check ownership and `isResolved` yourself, and call `resolve_review_thread` separately if the script would have. |
| `resolve_pr_review_thread.py` | `resolve_review_thread` | One thread per call, no `--all` |
| `unresolve_pr_review_thread.py` | `unresolve_review_thread` | |
| `post_issue_comment.py` | `add_issue_comment` | Works for PRs too |
| `new_issue.py` | `issue_write` method `create` | |
| `close_issue.py`, `reopen_issue.py` | `issue_write` method `update` | Set `state_reason` when closing |
| `set_issue_labels.py` | `issue_write` method `update` with `labels`, but read first | **Not equivalent, and destructive if used as one.** The script preserves unrelated labels, reconciles priority labels, and creates a label that does not exist yet. `issue_write` replaces the entire set and cannot create a missing label. So: read the current labels with `issue_read`, union your change into them, and send the whole result. If a label you need does not already exist on the repo, treat the operation as unavailable rather than dropping it silently. |
| `merge_pr.py` | `merge_pull_request` | |
| `set_pr_auto_merge.py` | `enable_pr_auto_merge`, `disable_pr_auto_merge` | Present in some toolsets and not others. Check yours before relying on it, and treat the operation as unavailable rather than substituting a merge. |
| `invoke_copilot_assignment.py` | `assign_copilot_to_issue` | |

## Operations with no MCP equivalent

These have no GitHub MCP operation. On a blocked session they cannot run at
all, so report them as unavailable rather than reporting a PR failure:

- Milestone **discovery** (`get_latest_semantic_milestone.py`). Nothing
  enumerates milestones, so the number cannot be looked up.

Two earlier entries here were wrong and are corrected rather than removed,
because a false "unavailable" disables a path that works:

- Reactions (`add_comment_reaction.py`) **are** available: `add_issue_comment`
  takes a `reaction` instead of a `body`, and a `comment_id` to react to one
  comment rather than the PR. The script's batch mode has no equivalent, so
  react one call at a time.
- Milestone **assignment** (`set_issue_milestone.py`, `set_item_milestone.py`)
  **is** available: `issue_write` method `update` takes a `milestone` number.
  You still need the number, which is the discovery gap above.
- Composite repo helpers that wrap several `gh` calls behind local logic and
  return a verdict: `why_pr_blocked.py`, `test_pr_merge_ready.py`,
  `check_pr_live_state.py`, `triage_red_check.py`, `run_completion_gate.py`,
  `check_pr_round_cap.py`, `pr_autofix_lease.py`. Their inputs can be gathered
  through the operations above, but the verdicts they compute are not available
  as a single call. Two of these gate mandatory steps: `check_pr_live_state.py`
  runs before every autofix action, and `triage_red_check.py` runs before any
  CI-failure log reading. Derive those verdicts by hand from fetched data and
  record that they were derived, rather than falling back to `gh`.

## Rules

1. Run the preflight once, before the first GitHub call, not per operation.
2. On `gh_unusable`, do not fall back to the `gh` scripts to double-check.
   They will fail, and their failure says nothing about the PR.
3. Do not report a PR as blocked, red, or unmergeable on the strength of a
   transport failure. An unreachable API is an unknown, not a verdict.
4. Do not paper over a gap in the table above by inventing an operation name.
   If an operation has no equivalent, say it is unavailable in this environment.
