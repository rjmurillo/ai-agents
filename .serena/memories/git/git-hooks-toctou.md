# TOCTOU Defense in Pre-Commit Hooks

**Statement**: Re-validate security checks in same process as action to prevent race conditions

**Context**: Security checks before file operations in hooks

**Evidence**: Security review identified TOCTOU vulnerability in symlink check

**Atomicity**: 96%

**Impact**: 9/10 (CRITICAL)

## Problem

Time-of-check to time-of-use race condition when security check runs in child process but action runs in parent.

## Anti-Pattern

```bash
RESULT=$(pwsh -File sync-script.ps1)  # Symlink check in PowerShell
git add -- "$FILE"                     # Action in bash - RACE WINDOW
```

## Solution - Defense-in-Depth

```bash
RESULT=$(pwsh -File sync-script.ps1)  # First check
if [ -L "$FILE" ]; then               # Defense-in-depth in bash
    echo "Error: symlink detected"
else
    git add -- "$FILE"                # Action in same process as check
fi
```

## Security Checklist

- [ ] Use `-NoProfile` with pwsh
- [ ] Reject symlinks (MEDIUM-002)
- [ ] Validate paths exist before use
- [ ] Quote all variables
- [ ] Use `--` separator for arguments

## Related

- [git-hooks-001-pre-commit-branch-validation](git-hooks-001-pre-commit-branch-validation.md)
- [git-hooks-002-branch-recovery-procedure](git-hooks-002-branch-recovery-procedure.md)
- [git-hooks-004-branch-name-validation](git-hooks-004-branch-name-validation.md)
- [git-hooks-autofix](git-hooks-autofix.md)
- [git-hooks-categories](git-hooks-categories.md)
