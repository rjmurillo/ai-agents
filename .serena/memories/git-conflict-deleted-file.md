# Deleted File Conflict Resolution

**Atomicity**: 88%
**Category**: Git Operations
**Source**: 2025-12-24 Parallel PR Review Retrospective

## Statement

When file deleted upstream and modified locally, accept deletion unless local changes needed.

## Context

During merge conflict resolution when git reports "CONFLICT (modify/delete)". Common in refactoring or file reorganization.

## Evidence

2025-12-24 Parallel PR Review: PR #255 skills-utilities.md deleted on main, modified on PR branch. Resolved by accepting deletion as file reorganization was intentional.

## Pattern

```bash
# 1. Identify conflict
git status  # Shows: "deleted by us" or "deleted by them"

# 2. Review local changes
git show HEAD:path/to/file

# 3. Decision:
if changes_obsolete; then
  git rm path/to/file  # Accept deletion
elif changes_needed; then
  git checkout --theirs path/to/file  # Restore
fi

git commit
```

## Decision Matrix

| Local Changes | Upstream Reason | Action |
|---------------|-----------------|--------|
| Obsolete | Refactoring | Accept deletion |
| Needed | Mistake | Restore file |
| Partial overlap | Consolidation | Manual merge |

## Related

- [git-003-staged-changes-guard](git-003-staged-changes-guard.md)
- [git-004-branch-switch-file-verification](git-004-branch-switch-file-verification.md)
- [git-004-branch-verification-before-commit](git-004-branch-verification-before-commit.md)
- [git-branch-cleanup-pattern](git-branch-cleanup-pattern.md)
- [git-conflict-resolution-workflow](git-conflict-resolution-workflow.md)
