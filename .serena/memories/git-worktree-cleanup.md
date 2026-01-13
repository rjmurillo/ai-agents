# Worktree Cleanup Automation

**Atomicity**: 91%
**Category**: Git Operations
**Source**: 2025-12-24 Parallel PR Review Retrospective

## Statement

Remove temporary worktrees at session end using `git worktree remove`.

## Context

At session end after all PR processing complete. Prevents technical debt accumulation from temporary worktrees.

## Evidence

2025-12-24 Parallel PR Review: Temporary worktree directories persisted after session, requiring manual cleanup.

## Pattern

```bash
# List and remove temporary worktrees
for wt in $(git worktree list | grep 'worktree-pr-' | awk '{print $1}'); do
  cd "$wt"
  if [ -z "$(git status --short)" ]; then
    cd -
    git worktree remove "$wt"
  else
    echo "SKIPPED (uncommitted changes): $wt"
  fi
done
```

## Safety Checks

| Check | Action if Failed |
|-------|------------------|
| Uncommitted changes | Skip removal, warn user |
| Unpushed commits | Skip removal, warn user |

## Related

- [git-003-staged-changes-guard](git-003-staged-changes-guard.md)
- [git-004-branch-switch-file-verification](git-004-branch-switch-file-verification.md)
- [git-004-branch-verification-before-commit](git-004-branch-verification-before-commit.md)
- [git-branch-cleanup-pattern](git-branch-cleanup-pattern.md)
- [git-conflict-deleted-file](git-conflict-deleted-file.md)
