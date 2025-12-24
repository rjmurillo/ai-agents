# AUTO-FIX Pattern for Pre-Commit

**Statement**: AUTO-FIX hooks should respect SKIP_AUTOFIX for CI "check only" mode

**Context**: Implementing auto-fix capability in pre-commit hooks

**Evidence**: ADR-004 and PR #52 implementation

**Atomicity**: 92%

**Impact**: 8/10

## Pattern

```bash
# At top of hook
AUTOFIX=1
if [ "${SKIP_AUTOFIX:-}" = "1" ]; then
    AUTOFIX=0
    echo "Auto-fix disabled (SKIP_AUTOFIX=1)"
fi

# In AUTO-FIX section
if [ "$AUTOFIX" = "1" ]; then
    if fix_tool "$FILES"; then
        git add -- "$FILES"  # git add is idempotent
        echo "Fixed and staged: $FILES"
    fi
fi
```

## Key Points

- `SKIP_AUTOFIX=1` disables auto-fix for CI "check only" mode
- `git add` is idempotent - safe to call on already-staged files
- Use unconditional `git add` to avoid untracked file detection issues
