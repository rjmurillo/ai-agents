# Security: Defenseindepth For Crossprocess Security Checks 94

## Skill-Security-007: Defense-in-Depth for Cross-Process Security Checks (94%)

**Statement**: Always re-validate security conditions in the process that performs the action, even if validation occurred in a child process

**Context**: When security validation (symlink check, path validation) runs in a subprocess and a subsequent action (file write, git add) runs in the parent

**Evidence**: PR #52 - PowerShell symlink check insufficient due to TOCTOU race window between pwsh completion and bash git add

**Atomicity**: 94%

**Tag**: helpful (security)

**Impact**: 9/10

**Pattern**:

```bash
# Child process validates
RESULT=$(pwsh -File sync-script.ps1)  # Symlink check here

# Parent MUST re-validate before action
if [ -L "$FILE" ]; then               # Defense-in-depth check
    echo "Error: symlink"
else
    git add -- "$FILE"                # Action in same process as check
fi
```

**Anti-Pattern**:

- Trusting child process security checks without re-validation
- Performing action in different process than security check

**Source**: `.agents/retrospective/pr-52-symlink-retrospective.md`

---

## Related

- [security-001-twophase-security-review](security-001-twophase-security-review.md)
- [security-002-input-validation-first-88](security-002-input-validation-first-88.md)
- [security-002-input-validation-first](security-002-input-validation-first.md)
- [security-003-secure-error-handling-90](security-003-secure-error-handling-90.md)
- [security-003-secure-error-handling](security-003-secure-error-handling.md)
