# Cross-Language Integration (Bash → PowerShell)

**Statement**: PowerShell `return` exits with code 0; use `exit N` for explicit exit codes

**Context**: Calling PowerShell scripts from bash pre-commit hooks

**Evidence**: PR #52 - Exit code semantics caused false positives

**Atomicity**: 94%

**Impact**: 8/10 (CRITICAL)

## Pattern

```bash
SCRIPT="$REPO_ROOT/scripts/Script.ps1"

# Security: Reject symlinks
if [ -L "$SCRIPT" ]; then
    echo "Warning: Script is a symlink"
else
    OUTPUT=$(pwsh -NoProfile -File "$SCRIPT" -PassThru 2>&1)
    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 0 ]; then
        # Use anchored grep for exact match
        if echo "$OUTPUT" | grep -q '^True$'; then
            FILES_FIXED=1
        fi
    fi
fi
```

## PowerShell Exit Code Semantics

| PowerShell | Bash Exit Code |
|------------|----------------|
| `return $true` | 0 |
| `return $false` | 0 (!) |
| `exit 0` | 0 |
| `exit 1` | 1 |
| Uncaught exception | Non-zero |

**CRITICAL**: Always use `exit N` for explicit exit codes, not `return`.

## Related

- [git-hooks-001-pre-commit-branch-validation](git-hooks-001-pre-commit-branch-validation.md)
- [git-hooks-002-branch-recovery-procedure](git-hooks-002-branch-recovery-procedure.md)
- [git-hooks-004-branch-name-validation](git-hooks-004-branch-name-validation.md)
- [git-hooks-autofix](git-hooks-autofix.md)
- [git-hooks-categories](git-hooks-categories.md)
