# github

Runs GitHub operations through Python scripts instead of raw `gh`. You get pull requests, issues, review threads, CI checks, labels, milestones, and merges, each with a JSON result and a stable exit code.

## When to use it

- You work with pull requests, issues, review comments, CI checks, or milestones.
- You say `create a PR`, `add label to issue`, `check CI status`, `respond to review comments`, or `close issue`.

## When not to use it

- You paste a `github.com` URL and want it read: use [`github-url-intercept`](github-url-intercept.md) instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:github`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the github skill to check CI status on PR 123.
```

The agent checks which transport works, picks the script that fits, runs it, and reads the JSON. You see the check results, or the error and its cause.

## What you get

Every script prints one JSON envelope (ADR-051):

```json
{
  "Success": true,
  "Data": { "Number": 42, "Title": "..." },
  "Error": null,
  "Metadata": { "Script": "get_pr_checks.py", "Version": "1.0.0", "Timestamp": "..." }
}
```

On failure, `Success` is `false` and `Error` carries `Message`, `Code`, and `Type`.

Exit codes follow ADR-035:

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Logic error |
| 2 | Config error |
| 3 | External failure |
| 4 | Auth error |

Some scripts add their own meaning to a code. For example, `triage_red_check.py` exits `0` when the check is green on main, `1` when it is red on main, and `3` when it cannot tell.

## Advanced use

**Pick a transport first.** `gh` can be installed and hold a token, yet be refused for a whole session (agent sandboxes that proxy egress do this). Run the preflight once, before the first GitHub call. From the root of a checkout of this repository:

```bash
uv run python .claude/skills/github/scripts/utils/check_github_transport.py
```

| Result | Do this |
| --- | --- |
| `Transport: gh` (exit 0) | Use the scripts. |
| `Transport: gh_unusable` (exit 0) | Route the work through the GitHub MCP operations. Do not retry the scripts. Confirm the operations you need are exposed first. |
| Exit 3 or 4 | Not a transport problem. It is a quota window or a fixable token. |

A transport failure is an unknown, never a verdict. Do not report a PR as blocked or red because the API was unreachable. The script-to-tool map is in [`transport-routing.md`](../../src/claude/skills/github/references/transport-routing.md).

Scripts share library discovery through the internal `skill_bootstrap.py` helper.
It checks plugin-root environment variables before using the caller's fallback.
It exits `2` when the selected library directory does not exist.

**Script groups.** Each group lives under `scripts/` in the skill:

| Group | Examples |
| --- | --- |
| `pr/` read | `get_pull_requests.py`, `get_pr_context.py`, `get_pr_checks.py`, `get_pr_check_logs.py`, `triage_red_check.py`, `get_pr_review_comments.py`, `get_pr_review_threads.py`, `get_pr_reviews.py`, `test_pr_merge_ready.py`, `why_pr_blocked.py` |
| `pr/` write | `new_pr.py`, `post_pr_comment_reply.py`, `add_pr_review_thread_reply.py`, `resolve_pr_review_thread.py`, `set_pr_auto_merge.py`, `update_pr_branch.py`, `rerun_failed_jobs.py`, `set_pr_ready.py`, `close_pr.py`, `merge_pr.py`, `edit_pr_title.py`, `dismiss_pr_review.py` |
| `issue/` | `get_issue_context.py`, `new_issue.py`, `close_issue.py`, `set_issue_labels.py`, `set_issue_milestone.py`, `post_issue_comment.py`, `set_issue_relationship.py`, `get_issue_relationships.py` |
| `milestone/` | `get_latest_semantic_milestone.py`, `set_item_milestone.py` |
| `reactions/` | `add_comment_reaction.py` (batch mode) |
| `notifications/` | `get_actionable_items.py` |
| `repo/` | `get_branch_protection.py` |
| `actions/` | `get_workflow_runs.py`, `get_workflow_run.py` |
| `utils/` | `check_github_transport.py`, `extract_github_context.py` |

The full parameter list is in [`script-catalog.md`](../../src/claude/skills/github/references/script-catalog.md). Gate scripts and their exit codes are in [`gate-script-usage.md`](../../src/claude/skills/github/references/gate-script-usage.md). Run any script with `--help` first:

```bash
uv run python .claude/skills/github/scripts/pr/get_pr_checks.py --help
uv run python .claude/skills/github/scripts/pr/new_pr.py --help
```

A read-only example, from a checkout:

```bash
uv run python .claude/skills/github/scripts/pr/get_pr_context.py --pull-request 123 --include-changed-files
```

`get_pr_checks.py` takes `--wait`, `--timeout-seconds`, `--required-only`, and `--output-format {json,human,auto}`. Keep `--wait` at or below 570 seconds, because the agent tool call is killed at 600 seconds. Under `--wait` it wakes early on a finished check suite or a push when `gh event listen` works (gh 2.105.0 or later, GitHub Event Streams access), and otherwise re-reads every 10 seconds; exit codes are the same either way.

**Required versus optional checks.** Only checks the base-branch ruleset requires block a merge. Pass `--required-only` and read `Data.RequiredState` to wait on those alone. An optional check, a job waiting on an environment approval, or a review bot that has not posted never holds a merge. See [`required-vs-optional-checks.md`](../../src/claude/skills/github/references/required-vs-optional-checks.md).

In a network-restricted sandbox, the read-only scripts under `scripts/pr/` run with a bare Python interpreter, not `uv run`. `uv run` resolves the whole project environment and times out with no network.

**Mutating scripts.** Most take `--dry-run`. `merge_pr.py` pins the merge to the reviewed head with `--expected-head-sha`, then reads back and audits the result. `update_pr_branch.py` and `set_pr_ready.py` return exit `1` with `head_moved` when the head differs from `--expected-head-sha`. `rerun_failed_jobs.py` returns exit `100` for `cannot_be_retried`. Never retry by pushing an empty commit.

**Issue provenance.** `new_issue.py` requires `--source`. Use `human` when an explicit human request selected the issue. Use `agent` for anything an agent chose, and add `--blocked-by` and `--signal` as Step 0 evidence. Blank answers or conflicting `source:*` labels exit `2` before any GitHub call. Raw `gh issue create` and the MCP `issue_write` tool bypass this check.

**Issue links.** A `#<number>` in an issue body sets no parent, dependency, or relation. Use `set_issue_relationship.py` with `--relation` set to `parent`, `sub-issue`, `blocked-by`, `blocking`, or `relates-to`. Pull requests cannot be linked this way. Use a closing keyword (`Closes`, `Fixes`, or `Resolves`) in the PR description instead. See [`issue-relationships.md`](../../src/claude/skills/github/references/issue-relationships.md).

**Common traps.**

- A reply to a review thread does not resolve it. When the thread is yours to resolve (bot-authored, or explicitly approved), call `resolve_pr_review_thread.py` after the reply. See [`pr-comment-responder`](pr-comment-responder.md).
- Post several reactions with batch mode in `add_comment_reaction.py`, not one call each.
- Use `--marker` on `post_issue_comment.py` to avoid duplicate comments.
- `mergeStateStatus: blocked` is a cached field. Run `why_pr_blocked.py` first. It names failing or missing required checks, unresolved threads, merge conflicts, and a review requesting changes. It counts that review only when the base branch has a `pull_request` ruleset rule. It does not read classic branch protection or required approval counts.

To test a workflow locally with `act`, the skill bundles `test_workflow_locally.py`:

```bash
uv run python .claude/skills/github/scripts/test_workflow_locally.py --help
```

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`github-url-intercept`](github-url-intercept.md): reads pasted GitHub URLs through the API.
- [`pr-comment-responder`](pr-comment-responder.md): works review threads using these scripts.
- [`push-pr`](push-pr.md): commits, pushes, and opens a PR.
- [`autoplan`](autoplan.md): routes PR, issue, label, and milestone requests here.
- Source: [`SKILL.md`](../../src/claude/skills/github/SKILL.md)
- Reference: [`api-reference.md`](../../src/claude/skills/github/references/api-reference.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
