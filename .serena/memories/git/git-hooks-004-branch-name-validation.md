# Skill-Git-Hooks-004: Branch Name Validation Pre-Commit Hook

**Atomicity**: 90%
**Category**: Git hooks, prevention
**Source**: PR #669 PR co-mingling retrospective

## Pattern

Pre-commit hook validates branch name matches expected pattern before allowing commits.

**Pre-commit Hook Implementation**:

```bash
#!/usr/bin/env bash
# .git/hooks/pre-commit

CURRENT_BRANCH=$(git branch --show-current)

# Valid patterns: feat/*, fix/*, chore/*, docs/*
if [[ ! "$CURRENT_BRANCH" =~ ^(feat|fix|chore|docs|refactor|test)/ ]]; then
  echo "ERROR: Invalid branch name: $CURRENT_BRANCH"
  echo "Expected pattern: {feat|fix|chore|docs|refactor|test}/description"
  exit 1
fi

# Block commits to main/master
if [[ "$CURRENT_BRANCH" =~ ^(main|master)$ ]]; then
  echo "ERROR: Cannot commit to branch '$CURRENT_BRANCH' directly"
  echo "HINT: Create a feature branch first (git checkout -b feat/description)"
  exit 1
fi

# Optional: Check against session log if exists
SESSION_LOG=$(find .agents/sessions -name "*.md" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)
if [[ -f "$SESSION_LOG" ]]; then
  DECLARED_BRANCH=$(grep -m1 "^\*\*Current\*\*:" "$SESSION_LOG" | sed 's/\*\*Current\*\*: //')
  if [[ -n "$DECLARED_BRANCH" && "$CURRENT_BRANCH" != "$DECLARED_BRANCH" ]]; then
    echo "ERROR: Branch mismatch"
    echo "  Current:  $CURRENT_BRANCH"
    echo "  Declared: $DECLARED_BRANCH"
    exit 1
  fi
fi

exit 0
```

## Problem

Commits to wrong branches occur when:

- Agent on unexpected branch (e.g., main, wrong feature branch)
- No runtime verification before commit
- Trust-based compliance fails

**Evidence**: PR #669 - 4 PRs contaminated due to wrong-branch commits

## Features

| Feature | Behavior |
|---------|----------|
| **Block main** | Reject commits to main/master (exit 1) |
| **Pattern validation** | Reject non-conventional branch names |
| **Session match** | Optional: verify against declared branch |
| **Clear messages** | Error + hint for blocked commits |

## Anti-Pattern

```bash
# WRONG: No branch validation
git commit -m "Fix issue"
# Commits to whatever branch is current, even if wrong

# WRONG: Bypass hook
git commit --no-verify -m "Quick fix"
# Defeats the protection mechanism
```

## Related Skills

- [git-004-branch-verification-before-commit](git-004-branch-verification-before-commit.md): Manual verification
- [session-init-003-branch-declaration](session-init-003-branch-declaration.md): Session log tracking
- [git-hooks-fix-hook-errors-never-bypass](git-hooks-fix-hook-errors-never-bypass.md): Never use --no-verify
- [protocol-013-verification-based-enforcement](protocol-013-verification-based-enforcement.md): Hook is enforcement mechanism

## References

- PR #669: PR co-mingling retrospective
- Issue #681: Pre-commit hook implementation
- Issue #684: SESSION-PROTOCOL branch verification

## Related

- [git-hooks-001-pre-commit-branch-validation](git-hooks-001-pre-commit-branch-validation.md)
- [git-hooks-002-branch-recovery-procedure](git-hooks-002-branch-recovery-procedure.md)
- [git-hooks-autofix](git-hooks-autofix.md)
- [git-hooks-categories](git-hooks-categories.md)
- [git-hooks-cross-language](git-hooks-cross-language.md)
