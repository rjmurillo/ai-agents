# Skill-Security-007: Defense-in-Depth for Cross-Process Security Checks

**Statement**: Always re-validate security conditions in the process that performs the action, even if validation occurred in a child process.

**Context**: When security validation (symlink check, path validation) runs in subprocess and action runs in parent

**Evidence**: PR #52 - PowerShell symlink check insufficient due to TOCTOU race window between pwsh completion and bash git add

**Atomicity**: 94%

**Pattern**:

```bash
# Child process validates
RESULT=$(pwsh -File sync-script.ps1)  # Symlink check here

# Parent MUST re-validate before action
if [ -L "$FILE" ]; then               # Defense-in-depth check
    echo "Error: symlink detected"
    exit 1
fi
git add -- "$FILE"                    # Action in same process as check
```

**Anti-Pattern**:

```bash
# WRONG: Trusting child process check
pwsh -File validate.ps1               # Check in subprocess
git add -- "$FILE"                    # Action without re-validation
# Race window between check and action!
```

**Source**: `.agents/retrospective/pr-52-symlink-retrospective.md`
