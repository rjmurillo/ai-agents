# Parallel Worktree Isolation

**Atomicity**: 94%
**Category**: Git Operations
**Source**: 2025-12-24 Parallel PR Review Retrospective

## Statement

Use git worktrees to isolate parallel PR processing and prevent cross-contamination.

## Context

When processing multiple PRs in single session. Creates isolated working directories for each PR branch.

## Evidence

2025-12-24 Parallel PR Review: 8 PRs processed in parallel via worktrees with zero cross-contamination. 92 comments across 8 PRs; 1.5 comments/minute throughput.

## Pattern

```bash
PR_NUMBER=123
BRANCH=$(gh pr view $PR_NUMBER --json headRefName -q '.headRefName')
git worktree add "/home/user/worktree-pr-$PR_NUMBER" "$BRANCH"

cd "/home/user/worktree-pr-$PR_NUMBER"
# ... process PR in isolation ...
```

## Metrics

| Metric | Value |
|--------|-------|
| Isolation success | 100% (zero cross-contamination) |
| Throughput | 1.5 comments/min |
| Parallel capacity | 8+ PRs |

## Related

- [git-003-staged-changes-guard](git-003-staged-changes-guard.md)
- [git-004-branch-switch-file-verification](git-004-branch-switch-file-verification.md)
- [git-004-branch-verification-before-commit](git-004-branch-verification-before-commit.md)
- [git-branch-cleanup-pattern](git-branch-cleanup-pattern.md)
- [git-conflict-deleted-file](git-conflict-deleted-file.md)
