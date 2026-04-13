# Bash Integration: Pattern Discovery & AUTOFIX

## Skill-Bash-Pattern-001: Pattern Discovery Protocol

**Statement**: Search file for 'AUTOFIX' before adding AUTO-FIX hook sections.

**Context**: When extending `.githooks/pre-commit` with new AUTO-FIX behavior.

**Evidence**: PR #52 Bug 1 - Added MCP sync without checking existing pattern at line 131.

**Atomicity**: 95%

### Prevention Pattern

```bash
# Before adding new AUTO-FIX section:
# 1. Search for existing patterns
grep -n "AUTOFIX" .githooks/pre-commit

# 2. Review existing patterns and follow same structure
# 3. Wrap new section in AUTOFIX check
```

## Skill-Process-PreCommit-001: AUTO-FIX Section Checklist

**Statement**: Wrap AUTO-FIX sections in `if [ "$AUTOFIX" = "1" ]` check.

**Atomicity**: 94%

### Checklist Before Adding AUTO-FIX Section

- [ ] Search for "AUTOFIX" in file: `grep -n "AUTOFIX" .githooks/pre-commit`
- [ ] Review existing AUTO-FIX patterns in the file
- [ ] Wrap new section in `if [ "$AUTOFIX" = "1" ]` check
- [ ] Add "skipped (auto-fix disabled)" message for SKIP_AUTOFIX case
- [ ] Verify exit code contract with any called scripts
- [ ] Test with `SKIP_AUTOFIX=1` to verify check-only mode

### Pattern

```bash
if [ -n "$STAGED_FILES_NEEDING_FIX" ]; then
    if [ "$AUTOFIX" = "1" ]; then
        echo "Auto-fixing files..."
        # Auto-fix logic here
    else
        echo "Auto-fix skipped (SKIP_AUTOFIX=1)."
    fi
fi
```
