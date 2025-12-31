# Skill-Git-Hooks-004: Branch Name Validation

**Statement**: Pre-commit hook validates branch name matches expected pattern

**Context**: Before any git commit (pre-commit hook execution)

**Evidence**: PR #669 analysis - automated validation catches wrong-branch errors before persistence

**Atomicity**: 90% | **Impact**: 9/10

## Pattern

**Pre-commit Hook Implementation**:

```bash
#!/usr/bin/env bash
# .git/hooks/pre-commit

CURRENT_BRANCH=$(git branch --show-current)

# Valid patterns: feat/*, fix/*, chore/*, docs/*
if [[ ! "$CURRENT_BRANCH" =~ ^(feat|fix|chore|docs)/ ]]; then
  echo "ERROR: Invalid branch name: $CURRENT_BRANCH"
  echo "Expected pattern: {feat|fix|chore|docs}/description"
  exit 1
fi

# Optional: Check against session log if exists
SESSION_LOG=$(find .agents/sessions -name "*.md" -type f -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2-)
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

- `git-004-branch-verification-before-commit`: Manual verification
- `session-init-003-branch-declaration`: Session log tracking
- `git-hooks-fix-hook-errors-never-bypass`: Never use --no-verify
