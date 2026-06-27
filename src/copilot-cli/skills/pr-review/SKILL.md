---
name: pr-review
description: Use when responding to PR review comments for specified pull request(s)
argument-hint: <PR_NUMBERS> [--parallel] [--cleanup] [--dry-run]
allowed-tools: Bash(git:*), Bash(gh:*), Bash(python3:*), Task, Skill, Read, Write, Edit, Glob, Grep
user-invocable: true
---

# PR Review Command

ultrathink

Respond to PR review comments for: the problem statement from the conversation (under Copilot CLI the skill tool takes no argument vector, so state it in your message)

Load configuration from `.claude/commands/pr-review-config.yaml` for scripts, completion criteria, error recovery, and failure handling tables.

## Context

- Current branch: !`git branch --show-current`
- Repository: !`gh repo view --json nameWithOwner -q '.nameWithOwner'`
- Authenticated as: !`gh api user -q '.login'`

## Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `PR_NUMBERS` | Comma-separated PR numbers or `all-open` | Required |
| `--parallel` | Use git worktrees for parallel execution | false |
| `--cleanup` | Clean up worktrees after completion | true |
| `--dry-run` | Preview planned actions without executing (JSON output) | false |

## Workflow

When `--dry-run` is specified, gather read-only context and output planned actions as JSON. See `dry_run` in config for output schema and constraints. Exit after output without executing mutations.

### Step 1: Parse and Validate PRs

For `all-open`, query open PRs. Cap the list to `invocation_limits.all_open_max_prs` from config (default: 5). If more open PRs exist, report the overflow count and execute `invocation_limits.all_open_overflow_action`.

For each PR number, validate using `scripts.claude_code.get_pr_context` from config.

Verify PR merge state using `scripts.claude_code.test_pr_merged`. Exit code 0 = not merged (safe), 1 = merged (skip). This avoids stale state from `gh pr view`.

### Step 2: Comprehensive PR Status Check

Before addressing comments, gather full context:

1. **Run Phase 0 thread clustering**: Use `cluster_threads` from config before the per-thread fix loop. If the JSON report has `warning: true`, add a `clusters` section to the verdict containing each cluster's `size`, `shared_tokens`, `source_artifact`, and `thread_ids`. Halt the per-thread loop. If `source_artifact` is non-null, patch that file's shared framing or spec source; otherwise patch the PR description, linked issue, or most common thread path after inspecting the cluster. Commit and push that cluster-level fix, then re-run the cluster step and resume per-file patches only after the warning is gone or the remaining threads no longer share one gist.
2. **Review ALL comments**: Use `get_review_threads`, `get_unresolved_threads`, `get_unaddressed_comments`, and `get_pr_context` scripts from config.
3. **Check merge eligibility**: Verify `mergeable=MERGEABLE` and no conflicts.
4. **Review failing checks**: Use `get_pr_checks` script. Handle failures per `check_failure_actions` table in config.

After you resolve the last thread on a PR with live bot reviewers (Copilot, Devin), do NOT trust a single `get_unresolved_threads` snapshot. A bot scan can land 30 to 120 seconds after your push and reopen the count. Run the `wait_for_settled_zero` script from config to confirm the count has settled: it polls and exits 0 only after three consecutive complete-and-zero readings 180s apart. This closes the bot-settle gap that produced the PR #1965 "0 unresolved" lie. The completion gate below is a one-shot verdict and does not settle over time.

### Step 3: Create Worktrees (if --parallel)

```bash
branch=$(gh pr view {number} --json headRefName -q '.headRefName')
git worktree add "./.worktrees/pr-{number}" "$branch"
```

### Step 4: Launch Agents

**Sequential**: Invoke `pr-comment-responder` skill for each PR with session context at `.agents/pr-comments/PR-{pr}/`.

**Parallel**: Launch background Task agents per PR. Wait for all with `TaskOutput`.

Each agent's intermediate output is subject to `output_constraints.per_pr_max_response_tokens` from config. If an agent approaches the token limit, summarize findings and move to the next PR.

### Step 5: Verify, Push, and Cleanup

Push any changes per worktree. Clean up worktrees if `--cleanup`. Check `worktree_constraints` in config for isolation rules.

### Step 6: Generate Summary

Report per-PR status using `output_constraints.summary_format` from config. Required columns: `output_constraints.summary_required_columns`. The only currently supported value of `summary_format` is `table`, so render a markdown table with one row per PR. If a future config introduces another value, update both this step and the allowed values in `output_constraints.summary_format` together.

## Thread Resolution

Replying does NOT resolve threads. Use `add_thread_reply_resolve` or separate `resolve_thread` calls. For batch resolution, use the GraphQL template in config.

## Completion Gate

The completion gate is dispatchable: each criterion in `completion_criteria` runs an external verification command, and the command's stdout JSON is the source of truth for the verdict. Run the dispatcher exactly once per PR:

```bash
uv run python .claude/skills/github/scripts/pr/run_completion_gate.py \
    --config .claude/commands/pr-review-config.yaml \
    --pull-request {pr} \
    --json
```

The dispatcher exits 0 if every criterion passes, 1 if any criterion fails, 2 on a config error. On failure, do NOT loop. Looping on a failing verifier produces the same wrong answer; the retry-on-failure behavior was the wrong design and has been removed (see retrospective `2026-05-05-pr-1887-iteration-paradox.md`, Layer 6: Reporting-Without-Acting Anti-Pattern).

When the dispatcher exits 1, surface the failing criterion's `name`, `command`, `reason`, and a stdout/stderr excerpt from the JSON output, then halt. Do not claim completion. Do not re-run the gate hoping for a different answer. Investigate the underlying failure and address it; once addressed, the gate may be re-run. The `--json` mode emits the verifier evidence inline; the table mode (default) prints the same fields below each FAIL row.

`fail_open: false` (the default for every criterion in this config) means a verifier that errors or returns malformed output also fails the gate. A verifier that cannot verify is not evidence that the criterion holds.

### Trust boundary on the PR branch

When `/pr-review` runs after `gh pr checkout`, the dispatcher reads `pr-review-config.yaml` from the PR's working tree. A malicious PR can change `completion_criteria.command` or `pass_when_python` and the dispatcher will execute it. Before invoking `/pr-review` on a PR that you do not control, INSPECT the diff for any change to `.claude/commands/pr-review-config.yaml`. The same caution applies to any test/lint/build a reviewer runs on a PR branch; this gate just makes the execution path explicit. Hardening (loading the config from `main` or refusing to run on divergence) is tracked as a follow-up to PR #1898.

## Related Memories

See `related_memories` in config for Serena memories to consult during PR review.
