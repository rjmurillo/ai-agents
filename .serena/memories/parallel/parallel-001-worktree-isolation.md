# Skill-Parallel-001: Worktree Isolation Pattern

## Statement

When creating worktrees for parallel PR work, use a dedicated parent directory and create local tracking branches to avoid detached HEAD state.

## Atomicity Score: 95%

## Impact: 8/10

## Context

Applies when launching parallel agents to work on multiple PRs simultaneously.

## Pattern

### Correct

```bash
# Create dedicated worktree directory
mkdir -p /home/claude/ai-agents-worktrees

# Create worktree with local tracking branch (avoids detached HEAD)
git fetch origin feature-branch
git worktree add -b pr-300 ../ai-agents-worktrees/pr-300 origin/feature-branch

# Agent working directory
cd /home/claude/ai-agents-worktrees/pr-300
git status  # Shows: On branch pr-300, tracking origin/feature-branch
```

### Incorrect

```bash
# Creates worktree in parent of repo (pollutes directory structure)
git worktree add ../worktree-pr-300 origin/feature-branch
# Results in: detached HEAD at commit hash
# Push requires: git push origin HEAD:feature-branch
```

## Why It Matters

1. **Detached HEAD confusion**: Agents don't know what branch they're on
2. **Push complexity**: Must specify remote branch explicitly
3. **Directory pollution**: Worktrees scattered in home directory
4. **Cleanup difficulty**: Hard to find and remove all worktrees

## Cleanup Pattern

```bash
# When done with parallel work
cd /home/claude/ai-agents  # Return to main repo
git worktree list          # See all worktrees
git worktree remove ../ai-agents-worktrees/pr-300  # Remove specific
rm -rf /home/claude/ai-agents-worktrees  # Remove parent when all done
```

## Evidence

Session 04 (2025-12-24): Created 4 worktrees at wrong location, all had detached HEAD, agents had to run extra checkout commands.

## Tags

- #parallel
- #worktree
- #git
- #agent-coordination

## Related

- [parallel-002-rate-limit-precheck](parallel-002-rate-limit-precheck.md)
