---
allowed-tools: Bash(git:*), Bash(gh:*), Bash(python3:*), Task, Skill, Read, Write, Edit, Glob, Grep
argument-hint: <PR_NUMBERS> [--parallel] [--cleanup] [--dry-run]
description: Use when responding to PR review comments for specified pull request(s)
---

# PR Review Command

ultrathink

Respond to PR review comments for: $ARGUMENTS

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

For `all-open`, query open PRs and cap the list at `invocation_limits.all_open_max_prs` from config. If additional PRs remain, record the skipped count and apply `invocation_limits.all_open_overflow_action` in Step 6. For each selected PR number, validate using `scripts.claude_code.get_pr_context` from config.

Verify PR merge state using `scripts.claude_code.test_pr_merged`. Exit code 0 = not merged (safe), 1 = merged (skip). This avoids stale state from `gh pr view`.

### Step 2: Comprehensive PR Status Check

Before addressing comments, gather full context:

1. **Review ALL comments**: Use `get_review_threads`, `get_unresolved_threads`, `get_unaddressed_comments`, and `get_pr_context` scripts from config.
2. **Check merge eligibility**: Verify `mergeable=MERGEABLE` and no conflicts.
3. **Review failing checks**: Use `get_pr_checks` script. Handle failures per `check_failure_actions` table in config.

### Step 3: Create Worktrees (if --parallel)

```bash
branch=$(gh pr view {number} --json headRefName -q '.headRefName')
git worktree add "./.worktrees/pr-{number}" "$branch"
```

### Step 4: Launch Agents

**Sequential**: Invoke `pr-comment-responder` skill for each PR with session context at `.agents/pr-comments/PR-{pr}/`.

**Parallel**: Launch background Task agents per PR. Wait for all with `TaskOutput`.

### Step 5: Verify, Push, and Cleanup

Push any changes per worktree. Clean up worktrees if `--cleanup`. Check `worktree_constraints` in config for isolation rules.

### Step 6: Generate Summary

Report per-PR status using `output_constraints.summary_format` from config with columns from `output_constraints.summary_required_columns`. Truncate per-PR agent output exceeding `output_constraints.per_pr_max_response_lines` and persist full detail per `output_constraints.per_pr_overflow_action`. If `all-open` skipped PRs in Step 1, append a row noting the skipped count and direct the user to re-run.

## Thread Resolution

Replying does NOT resolve threads. Use `add_thread_reply_resolve` or separate `resolve_thread` calls. For batch resolution, use the GraphQL template in config.

## Completion Gate

ALL criteria from `completion_criteria` in config must pass before claiming completion. If ANY fails, loop back. Enforce `invocation_limits.completion_gate_max_retries` as the maximum number of retries after the initial failed completion check (i.e., initial check + N retries = N+1 total attempts). After the retry cap is exhausted, apply `invocation_limits.completion_gate_overflow_action`: halt the loop, record which criteria still fail, and escalate to the user. See `failure_handling` and `error_recovery` in config for recovery actions.

## Related Memories

See `related_memories` in config for Serena memories to consult during PR review.
