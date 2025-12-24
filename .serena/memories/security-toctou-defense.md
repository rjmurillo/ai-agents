# Security TOCTOU Defense

## Skill-Security-007: Defense-in-Depth for Cross-Process Security Checks (94%)

**Statement**: Always re-validate security conditions in the process that performs the action, even if validation occurred in a child process.

**Context**: When security validation (symlink check, path validation) runs in subprocess and action runs in parent

**Evidence**: PR #52 - PowerShell symlink check insufficient due to TOCTOU race window between pwsh completion and bash git add

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

## Skill-Security-008: First-Run Gap Analysis (91%)

**Statement**: When reviewing conditional security checks, verify they cover creation scenarios, not just modification scenarios.

**Context**: When security code uses existence checks (`if file exists then validate`)

**Evidence**: PR #52 - `if (Test-Path $DestinationPath)` meant symlink check only ran on updates, not creates

**Pattern**:

```powershell
# WRONG: Only validates when file exists
if (Test-Path $Path) {
    if ((Get-Item $Path).LinkType) { throw "symlink" }
}
# First-run creates file without validation!

# RIGHT: Validate after creation too
$result = Create-File $Path
if ((Get-Item $Path).LinkType) { throw "symlink detected" }
```

**Checklist**:

- [ ] Does security check run on file creation?
- [ ] Does security check run on file modification?
- [ ] Does security check run on file deletion?
- [ ] Is there a gap between check and action?

**Source**: `.agents/retrospective/pr-52-symlink-retrospective.md`
