---
argument-hint: <PR_NUMBERS> [--parallel] [--cleanup]
description: Use when responding to PR review comments for specified pull request(s)
tools:
  - vscode
  - execute
  - read
  - agent
  - edit
  - search
  - web
  - forgetful/*
  - serena/*
  - todo
  - updateUserPreferences
  - memory
model: Claude Opus 4.5 (copilot)
---

# PR Review Command

ultrathink

Respond to PR review comments for: $ARGUMENTS

Load configuration from `.claude/commands/pr-review-config.yaml` for scripts (use `scripts.copilot` section), completion criteria, error recovery, and failure handling tables.

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

## Workflow

### Step 1: Parse and Validate PRs

For `all-open`, query open PRs. For each PR number, validate using `scripts.copilot.get_pr_context` from config.

Verify PR merge state using `scripts.copilot.test_pr_merged`. Exit code 0 = not merged (safe), 1 = merged (skip). This avoids stale state from `gh pr view`.

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

**Parallel**: Launch background agents per PR. Wait for all to complete.

### Step 5: Verify, Push, and Cleanup

Push any changes per worktree. Clean up worktrees if `--cleanup`. Check `worktree_constraints` in config for isolation rules.

### Step 6: Generate Summary

Report per-PR status table: PR, Branch, Comments, Acknowledged, Implemented, Commit, Status.

## Thread Resolution

Replying does NOT resolve threads. Use `add_thread_reply` then `resolve_thread` calls. For batch resolution, use the GraphQL template in config.

## Completion Gate

ALL criteria from `completion_criteria` in config must pass before claiming completion. If ANY fails, loop back. See `failure_handling` and `error_recovery` in config for recovery actions.

## Related Memories

See `related_memories` in config for Serena memories to consult during PR review.
