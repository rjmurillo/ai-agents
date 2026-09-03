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
| Copilot CLI | `github/pull_request_read` (see `templates/toolsets.yaml`) |

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
rather than the session. Only a refusal seen on both transports proves the
session is blocked.

`gh` stays the default everywhere it works, notably CI, where Actions supplies
a working token. Nothing here removes `gh` from those environments.

## Script to MCP operation

Read operations:

| Instead of | Use | Notes |
|------------|-----|-------|
| `get_pr_context.py` | `pull_request_read` method `get` | |
| `get_pr_context.py --include-diff` | `pull_request_read` method `get_diff` | |
| `get_pull_requests.py` | `list_pull_requests`, or `search_pull_requests` for filters | |
| `get_pr_checks.py` | `pull_request_read` method `get_check_runs` | `get_check_run` fetches one run's output text |
| `get_pr_check_logs.py` | `get_job_logs` | Set `failed_only` to skip green jobs |
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
| `post_pr_comment_reply.py` | `add_reply_to_pull_request_comment` | |
| `add_pr_review_thread_reply.py` | `add_reply_to_pull_request_comment` | |
| `resolve_pr_review_thread.py` | `resolve_review_thread` | One thread per call, no `--all` |
| `unresolve_pr_review_thread.py` | `unresolve_review_thread` | |
| `post_issue_comment.py` | `add_issue_comment` | Works for PRs too |
| `new_issue.py` | `issue_write` method `create` | |
| `close_issue.py`, `reopen_issue.py` | `issue_write` method `update` | Set `state_reason` when closing |
| `set_issue_labels.py` | `issue_write` method `update` with `labels` | Replaces the set, not additive |
| `merge_pr.py` | `merge_pull_request` | |
| `set_pr_auto_merge.py` | `enable_pr_auto_merge`, `disable_pr_auto_merge` | |
| `invoke_copilot_assignment.py` | `assign_copilot_to_issue` | |

## Operations with no MCP equivalent

These have no GitHub MCP operation. On a blocked session they cannot run at
all, so report them as unavailable rather than reporting a PR failure:

- Reactions (`add_comment_reaction.py`). No reactions tool exists.
- Milestones (`set_issue_milestone.py`, `get_latest_semantic_milestone.py`,
  `set_item_milestone.py`). No milestone tool exists.
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
