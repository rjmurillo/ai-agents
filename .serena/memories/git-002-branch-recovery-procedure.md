# Skill-Git-002: Branch Recovery from Main Commit

**Statement**: Move commits from main to feature branch: create branch from HEAD, reset main to origin, checkout branch

**Context**: When accidentally committed to main/master instead of feature branch

**Trigger**: After realizing commit was made to protected branch

**Evidence**: Session 04 - Committed to main by mistake, recovered using this procedure

**Atomicity**: 70%

**Tag**: helpful

**Impact**: 8/10

**Created**: 2025-12-24

**Validated**: 1

**Category**: Git

## Recovery Procedure

### Step 1: Create Branch from Current State

```bash
# Preserve work by creating branch from HEAD
git checkout -b feat/issue-NNN-description
```

This captures all commits currently on main.

### Step 2: Reset Main to Origin

```bash
# Switch back to main
git checkout main

# Reset to remote state (discards local commits)
git reset --hard origin/main
```

This removes the accidental commits from main.

### Step 3: Return to Feature Branch

```bash
# Switch back to feature branch with your work
git checkout feat/issue-NNN-description
```

Work is now on feature branch, main is clean.

## Visual Example

**Before Recovery**:
```
main:    A---B---C---D (accidental commit D)
origin:  A---B---C
```

**After Recovery**:
```
main:              A---B---C (reset to origin)
feat/issue-NNN:    A---B---C---D (work preserved)
origin:            A---B---C
```

## Why This Works

- `git checkout -b` creates branch pointing to current HEAD (preserves work)
- `git reset --hard origin/main` rewinds main to match remote (removes mistake)
- Original commits preserved on feature branch, ready for PR

## Prevention Pattern

Use **skill-git-001-pre-commit-branch-validation** to prevent this scenario:

```bash
# Before committing, check branch
CURRENT_BRANCH=$(git branch --show-current)
if [[ "$CURRENT_BRANCH" == "main" ]]; then
    git checkout -b feat/issue-NNN-description
fi
```

## When to Apply

AFTER:
- Realizing commit was made to main/master
- Before pushing to remote
- Before making additional commits

NOT APPLICABLE:
- After pushing to remote (requires different recovery)
- When working on intended main branch
- When main is not protected

## Success Criteria

- Work preserved on feature branch
- Main branch matches origin
- No commits lost
- Ready to create PR from feature branch

## Related Skills

- skill-git-001-pre-commit-branch-validation: Prevention (BEFORE commit)
- skill-git-002-branch-recovery-procedure: Recovery (AFTER commit)
- agent-workflow-atomic-commits: Commit discipline

## Anti-Pattern

**DON'T** force push to main:
```bash
# WRONG - pollutes main history
git push --force origin main
```

**DO** recover to feature branch:
```bash
# CORRECT - preserves work, cleans main
git checkout -b feat/issue-NNN
git checkout main
git reset --hard origin/main
```
