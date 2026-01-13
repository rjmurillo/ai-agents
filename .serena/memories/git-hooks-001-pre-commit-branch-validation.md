# Skill: Git-001 Pre-Commit Branch Validation

**Atomicity Score**: 90%
**Source**: Session 04 retrospective - User correction
**Date**: 2025-12-24
**Validation Count**: 1 (Session 04 main commit violation)
**Tag**: helpful
**Impact**: 9/10 (Prevents main branch pollution, critical safety)

## Statement

Check branch name before committing - prevent commits to main/master.

## Context

Before EVERY git commit operation, especially in automated workflows or agent sessions.

## Evidence

Session 04 incident: Agent committed to `main` branch instead of feature branch. User correction required manual cleanup.

## Implementation Pattern

### Pre-Commit Check

```bash
# Check current branch before committing
CURRENT_BRANCH=$(git branch --show-current)

if [[ "$CURRENT_BRANCH" == "main" || "$CURRENT_BRANCH" == "master" ]]; then
    echo "::error::Cannot commit to protected branch: $CURRENT_BRANCH"
    echo "::error::Create feature branch first: git checkout -b feat/issue-NNN-description"
    exit 1
fi

# Safe to commit
git commit -m "message"
```

### Git Hook Alternative

```bash
# .git/hooks/pre-commit
#!/bin/bash
BRANCH=$(git branch --show-current)

if [[ "$BRANCH" =~ ^(main|master)$ ]]; then
    echo "ERROR: Direct commits to $BRANCH are not allowed"
    echo "Create a feature branch instead"
    exit 1
fi
```

## Why This Matters

### Without Check (Anti-pattern)

```bash
# Dangerous: No branch validation
git add .
git commit -m "fix bug"  # Could be on main!
git push
# Oops - pushed to main, broke CI, pollution in history
```

### With Check (Correct Pattern)

```bash
# Safe: Validate branch first
CURRENT_BRANCH=$(git branch --show-current)
if [[ "$CURRENT_BRANCH" == "main" ]]; then
    git checkout -b "feat/issue-123-fix-bug"
fi

git commit -m "fix bug"  # Safe - on feature branch
```

## When to Use

Apply BEFORE:
- Every `git commit` command
- Automated commit workflows
- Agent-driven commits
- Multi-agent coordination sessions

Especially critical in:
- CI/CD pipelines
- Automation scripts
- Agent implementations
- Bot workflows

## Related Skills

- skill-coordination-001-branch-isolation-gate: Multi-agent branch verification
- agent-workflow-atomic-commits: Commit discipline
- git-hooks-categories: Git hook patterns

## Success Criteria

- Zero accidental commits to main/master
- Early failure with clear error message
- Forces feature branch creation
- Prevents main branch pollution
- Reduces cleanup burden

## Common Violations

Watch for:
- Clone operations default to main
- `git checkout main` in scripts
- Missing branch creation step
- Agent initialization on main
- Session start without branch check

## Related

- [git-hooks-002-branch-recovery-procedure](git-hooks-002-branch-recovery-procedure.md)
- [git-hooks-004-branch-name-validation](git-hooks-004-branch-name-validation.md)
- [git-hooks-autofix](git-hooks-autofix.md)
- [git-hooks-categories](git-hooks-categories.md)
- [git-hooks-cross-language](git-hooks-cross-language.md)
