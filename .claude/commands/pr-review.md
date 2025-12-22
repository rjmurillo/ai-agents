---
allowed-tools: Bash(git:*), Bash(gh:*), Bash(pwsh:*), Task, Skill, Read, Write, Edit, Glob, Grep
argument-hint: <PR_NUMBERS> [--parallel] [--cleanup]
description: Respond to PR review comments for the specified pull request(s)
---

# PR Review Command

Respond to PR review comments for the specified pull request(s): $ARGUMENTS

## Context

- Current branch: !`git branch --show-current`
- Repository: !`gh repo view --json nameWithOwner -q '.nameWithOwner'`
- Authenticated as: !`gh api user -q '.login'`

## Arguments

Parse the input: `$ARGUMENTS`

| Argument | Description | Default |
|----------|-------------|---------|
| `PR_NUMBERS` | Comma-separated PR numbers (e.g., `53,141,143`) or `all-open` | Required |
| `--parallel` | Use git worktrees for parallel execution | false |
| `--cleanup` | Clean up worktrees after completion | true |

## Workflow

### Step 1: Parse and Validate PRs

For `all-open`, query: `gh pr list --state open --json number,reviewDecision`

For each PR number, validate using:

```powershell
pwsh .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest {number}
```

Verify: PR exists, is open (state != MERGED, CLOSED), targets current repo.

### Step 2: Create Worktrees (if --parallel)

For parallel execution:

```bash
branch=$(gh pr view {number} --json headRefName -q '.headRefName')
git worktree add "../worktree-pr-{number}" "$branch"
```

### Step 3: Launch Agents

**Sequential (default):**

```python
for pr in pr_numbers:
    Skill(skill="pr-comment-responder", args=str(pr))
```

**Parallel (--parallel):**

```python
agents = []
for pr in pr_numbers:
    agent = Task(
        subagent_type="pr-comment-responder",
        prompt=f"PR #{pr}",
        run_in_background=True
    )
    agents.append(agent)

for agent_id in agents:
    TaskOutput(task_id=agent_id, block=True, timeout=600000)
```

### Step 4: Verify and Push

For each worktree:

```bash
cd "../worktree-pr-{number}"
if [[ -n "$(git status --short)" ]]; then
    git add .
    git commit -m "chore(pr-{number}): finalize review response session"
    git push origin "$branch"
fi
```

### Step 5: Cleanup Worktrees (if --cleanup)

```bash
cd "{main_repo}"
for pr in $pr_numbers; do
    worktree_path="../worktree-pr-${pr}"
    cd "$worktree_path"
    status="$(git status --short)"
    if [[ -z "$status" ]]; then
        cd "{main_repo}"
        git worktree remove "$worktree_path"
    else
        echo "WARNING: worktree-pr-${pr} has uncommitted changes"
    fi
done
```

### Step 6: Generate Summary

Output:

```markdown
## PR Review Summary

| PR | Branch | Comments | Acknowledged | Implemented | Commit | Status |
|----|--------|----------|--------------|-------------|--------|--------|
| #53 | feat/xyz | 4 | 4 | 3 | abc1234 | COMPLETE |

### Statistics
- **PRs Processed**: N
- **Comments Reviewed**: N
- **Fixes Implemented**: N
- **Commits Pushed**: N
- **Worktrees Cleaned**: N
```

## Error Recovery

| Scenario | Action |
|----------|--------|
| PR not found | Log warning, skip PR, continue |
| Branch conflict | Log error, skip PR, continue |
| Agent timeout | Log partial status, force cleanup |
| Push rejection | Detect concurrent updates (fetch and compare remote). If no concurrent changes, retry with `--force-with-lease`; otherwise, log rejection and require manual resolution (do not force push in parallel scenarios). |
| Merge conflict | Log conflict, skip cleanup, report for manual resolution |

## Critical Constraints (MUST)

When using `--parallel` with worktrees:

1. **Worktree Isolation**: ALL changes MUST be contained within the assigned worktree
2. **Working Directory**: Agents MUST set working directory to their worktree before file operations
3. **Path Validation**: All file paths MUST be relative to worktree root
4. **Git Operations**: Git commands MUST be executed from within the worktree directory
5. **Verification Gate**: Before cleanup, verify no files were written outside worktrees

## Examples

```bash
/pr-review 194                              # Single PR
/pr-review 53,141,143                       # Multiple PRs sequentially
/pr-review 53,141,143 --parallel            # Multiple PRs in parallel
/pr-review all-open --parallel              # All open PRs needing review
/pr-review 194 --parallel --cleanup=false   # Skip cleanup
```
