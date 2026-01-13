# Skill-Git-004: Branch Verification Before Commit

**Statement**: Before ANY mutating git operation (commit, push, reset), MUST run `git branch --show-current`

**Context**: Before git commit, git push, git reset, or any operation that persists changes

**Evidence**: PR #669 co-mingling analysis - prevented 100% of wrong-branch commits when enforced

**Atomicity**: 92% | **Impact**: 10/10

## Pattern

```bash
# 1. ALWAYS verify current branch first
git branch --show-current

# 2. Confirm output matches intended PR/issue branch
# Expected: feat/issue-XXX or feat/descriptive-name
# If mismatch: STOP - do not proceed with mutating operation

# 3. Only after verification, proceed with operation
git commit -m "..."
# OR
git push
# OR
git reset --hard
```

## Anti-Pattern

```bash
# WRONG: Assume you're on the right branch
git commit -m "Fix issue #123"

# WRONG: Skip verification for "quick" commits
git add . && git commit -m "Quick fix"

# WRONG: Trust previous branch switches
git checkout feat/new-feature
# ... later in session ...
git commit -m "..."  # No verification!
```

## Related Skills

- [git-hooks-004-branch-name-validation](git-hooks-004-branch-name-validation.md): Pre-commit hook enforcement
- [session-init-003-branch-declaration](session-init-003-branch-declaration.md): Session-level branch tracking
- [protocol-013-verification-based-enforcement](protocol-013-verification-based-enforcement.md): Design principle

## Related

- [git-003-staged-changes-guard](git-003-staged-changes-guard.md)
- [git-004-branch-switch-file-verification](git-004-branch-switch-file-verification.md)
- [git-branch-cleanup-pattern](git-branch-cleanup-pattern.md)
- [git-conflict-deleted-file](git-conflict-deleted-file.md)
- [git-conflict-resolution-workflow](git-conflict-resolution-workflow.md)
