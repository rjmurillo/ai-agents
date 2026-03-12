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

### Dry-Run Mode (--dry-run)

When `--dry-run` is specified, the command gathers all planned actions without executing any GitHub mutations.

**What happens in dry-run mode:**

1. Parse and validate PR numbers (same as normal)
2. Gather PR context, comments, and check status (read-only API calls)
3. Analyze what actions would be taken
4. Output planned actions as JSON to stdout

**What does NOT happen in dry-run mode:**

- No comments are posted
- No reactions are added
- No labels are applied
- No threads are resolved
- No commits are made
- No git push operations

**JSON Output Format:**

```json
{
  "dry_run": true,
  "timestamp": "2026-01-19T12:00:00Z",
  "prs": [
    {
      "number": 123,
      "branch": "feat/example",
      "state": "OPEN",
      "mergeable": "MERGEABLE",
      "planned_actions": {
        "comments_to_post": [
          {
            "thread_id": "PRRT_xxx",
            "reply_body": "Addressed in commit abc1234",
            "resolve_thread": true
          }
        ],
        "reactions_to_add": [
          {
            "comment_id": "IC_abc123",
            "reaction": "eyes"
          }
        ],
        "labels_to_apply": ["needs-review"],
        "status_updates": [
          {
            "action": "resolve_thread",
            "thread_id": "PRRT_yyy"
          }
        ]
      },
      "unaddressed_comments": [
        {
          "id": "IC_abc123",
          "author": "reviewer",
          "body": "Please fix this issue",
          "domain": "Bug",
          "priority": "P1"
        }
      ],
      "failing_checks": [
        {
          "name": "AI Quality Gate",
          "conclusion": "FAILURE",
          "suggested_action": "Address code quality findings"
        }
      ]
    }
  ],
  "summary": {
    "total_prs": 1,
    "total_comments_to_address": 3,
    "total_planned_replies": 2,
    "total_threads_to_resolve": 2
  }
}
```

**Dry-run workflow:**

```bash
# Step 1: Parse PR numbers (same as normal)
# Step 2: For each PR, gather read-only context

for pr in pr_numbers:
    # Get PR context (read-only)
    context=$(python3 .claude/skills/github/scripts/pr/get_pr_context.py --pull-request $pr)

    # Get all comments (read-only)
    comments=$(python3 .claude/skills/github/scripts/pr/get_pr_review_comments.py --pull-request $pr --group-by-domain --include-issue-comments)

    # Get unaddressed comments (read-only)
    unaddressed=$(python3 .claude/skills/github/scripts/pr/get_unaddressed_comments.py --pull-request $pr)

    # Get failing checks (read-only)
    checks=$(python3 .claude/skills/github/scripts/pr/get_pr_checks.py --pull-request $pr)

    # Analyze and collect planned actions (no mutations)
    # Output JSON with planned actions
done

# Output consolidated JSON to stdout
```

**Usage examples:**

```bash
# Preview actions for a single PR
/pr-review 123 --dry-run

# Preview actions for multiple PRs
/pr-review 123,456,789 --dry-run

# Preview all open PRs
/pr-review all-open --dry-run
```

**Exit after dry-run:** When `--dry-run` is specified, output the JSON and exit. Do not proceed to actual execution steps.

### Step 1: Parse and Validate PRs

For `all-open`, query open PRs. For each PR number, validate using `scripts.claude_code.get_pr_context` from config.

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

Report per-PR status table: PR, Branch, Comments, Acknowledged, Implemented, Commit, Status.

## Thread Resolution

Replying does NOT resolve threads. Use `add_thread_reply_resolve` or separate `resolve_thread` calls. For batch resolution, use the GraphQL template in config.

## Completion Gate

ALL criteria from `completion_criteria` in config must pass before claiming completion. If ANY fails, loop back. See `failure_handling` and `error_recovery` in config for recovery actions.

## Related Memories

See `related_memories` in config for Serena memories to consult during PR review.
