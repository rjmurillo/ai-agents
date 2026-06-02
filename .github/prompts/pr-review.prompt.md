---
argument-hint: <PR_NUMBERS> [--parallel] [--cleanup] [--dry-run]
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
| `--dry-run` | Preview planned actions without executing | false |

## Workflow

### Step 1: Parse and Validate PRs

For `all-open`, query open PRs. For each PR number, validate using `scripts.copilot.get_pr_context` from config.

Verify PR merge state using `scripts.copilot.test_pr_merged`. Exit code 0 = not merged (safe), 1 = merged (skip). This avoids stale state from `gh pr view`.

### Step 2: Comprehensive PR Status Check

Before addressing comments, gather full context:

1. **Run Phase 0 thread clustering**: Use `cluster_threads` from config before the per-thread fix loop. If the JSON report has `warning: true`, surface the clusters in the verdict with `size`, `shared_tokens`, `source_artifact`, and `thread_ids`; stop the per-thread loop and fix the cluster-level framing or spec source first. Resume per-file patches only after that cluster-level fix is pushed.
2. **Review ALL comments**: Use `get_review_threads`, `get_unresolved_threads`, `get_unaddressed_comments`, and `get_pr_context` scripts from config.
3. **Check merge eligibility**: Verify `mergeable=MERGEABLE` and no conflicts.
4. **Review failing checks**: Use `get_pr_checks` script. Handle failures per `check_failure_actions` table in config.

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

The completion gate is dispatchable. Each criterion in `completion_criteria` runs an external command, and the command's stdout JSON drives the verdict via the `pass_when` expression. Run the dispatcher exactly once per PR:

```bash
python3 .claude/skills/github/scripts/pr/run_completion_gate.py \
    --config .claude/commands/pr-review-config.yaml \
    --pull-request {pr} \
    --json
```

Exit 0 = all criteria passed; exit 1 = at least one failed; exit 2 = config error. On failure, do NOT loop. The retry-on-failure behavior was the wrong design and has been removed (see retrospective `2026-05-05-pr-1887-iteration-paradox.md`, Layer 6: Reporting-Without-Acting Anti-Pattern). Surface the failing criterion's `name`, `command`, `reason`, and stdout/stderr excerpt from the JSON output, then halt. The default table mode prints the same fields below each FAIL row.

### Trust boundary on the PR branch

When `/pr-review` runs after `gh pr checkout`, the dispatcher reads `pr-review-config.yaml` from the PR's working tree. A malicious PR can change `completion_criteria.command` or `pass_when_python` and the dispatcher will execute it. Before invoking `/pr-review` on a PR that you do not control, INSPECT the diff for any change to `.claude/commands/pr-review-config.yaml`. Hardening (loading the config from `main` or refusing to run on divergence) is tracked as a follow-up to PR #1898.

## Related Memories

See `related_memories` in config for Serena memories to consult during PR review.
