# Transport Routing

Which GitHub transport works is a property of the environment, not of the
operation. Decide it once per session with the preflight, then stop
re-deciding it per call.

```bash
uv run python .claude/skills/github/scripts/utils/check_github_transport.py
```

| Verdict | Meaning | What to do |
|---------|---------|------------|
| `Transport: gh` | `gh` holds a working credential | Use the scripts in this skill. Nothing changes. |
| `Transport: mcp` | `gh` cannot reach GitHub for this whole session | Use the `mcp__github__*` tools below. |
| exit 3 | Quota refusal or transport wobble | Not a transport problem. Wait and retry on `gh`. |
| exit 4 | Credential fault the operator can fix | Not a transport problem. Fix the token. |

## Why gh can be installed and still unusable

An agent sandbox that proxies egress (Claude Code on the web, for example)
leaves `gh` on PATH and `GH_TOKEN` set, then refuses GitHub for the session:

```text
gh: GitHub access is not enabled for this session. An org admin must connect
the Claude GitHub App for this organization. (HTTP 403)
```

`gh auth login` cannot clear this and neither can retrying, because the
credential is not what is being refused. The preflight reports this condition
as the auth status `transport_blocked`.

`gh` stays the default everywhere it works, notably CI, where Actions supplies
a working token. Nothing here removes `gh` from those environments.

## Script to MCP tool

Read operations:

| Instead of | Use | Notes |
|------------|-----|-------|
| `get_pr_context.py` | `pull_request_read` method `get` | |
| `get_pr_context.py --diff` | `pull_request_read` method `get_diff` | |
| `get_pull_requests.py` | `list_pull_requests`, or `search_pull_requests` for filters | |
| `get_pr_checks.py` | `pull_request_read` method `get_check_runs` | `get_check_run` for one run |
| `get_pr_check_logs.py` | `get_job_logs` | Set `failed_only` to skip green jobs |
| `get_pr_review_comments.py` | `pull_request_read` method `get_review_comments` | Returns threads with `isResolved` |
| `get_pr_reviews.py` | `pull_request_read` method `get_reviews` | |
| `get_pr_reviewers.py` | `get_reviews` plus `get_review_comments`, unioned | No single-call equivalent |
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

These have no `mcp__github__*` tool. On a blocked session they cannot run at
all, so report them as unavailable rather than reporting a PR failure:

- Reactions (`add_comment_reaction.py`). No reactions tool exists.
- Milestones (`set_issue_milestone.py`, `get_latest_semantic_milestone.py`,
  `set_item_milestone.py`). No milestone tool exists.
- Composite repo helpers that wrap several `gh` calls behind local logic:
  `why_pr_blocked.py`, `test_pr_merge_ready.py`, `triage_red_check.py`,
  `run_completion_gate.py`, `check_pr_round_cap.py`, `pr_autofix_lease.py`.
  Their inputs can be gathered through the tools above, but the verdicts they
  compute are not available as a single call.

## Rules

1. Run the preflight once, before the first GitHub call, not per operation.
2. On `Transport: mcp`, do not fall back to the `gh` scripts to double-check.
   They will fail, and their failure says nothing about the PR.
3. Do not report a PR as blocked, red, or unmergeable on the strength of a
   transport failure. An unreachable API is an unknown, not a verdict.
4. Do not paper over a gap in the table above by inventing a tool name. If an
   operation has no equivalent, say it is unavailable in this environment.
