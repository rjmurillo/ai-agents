# Bash Integration: Exit Codes & Cross-Language Contract

## Skill-PowerShell-ExitCode-001: Script Scope Return Semantics

**Statement**: In PowerShell script scope use `exit` not `return`; `return` exits with code 0.

**Context**: When PowerShell script is invoked from bash and exit codes matter.

**Evidence**: PR #52 Bug 2 - Lines 88, 95, 105, 111 used `return $false` which exits code 0.

**Atomicity**: 92%

### Key Insight

- `return` in **function scope**: Returns value to caller, function exits
- `return` in **script scope**: Entire script exits with code 0 (regardless of value)
- `exit N` in **script scope**: Script exits with code N

### Antipattern (DO NOT USE)

```powershell
# WRONG - return exits script with code 0, exit 1 is unreachable
if (-not (Test-Path $SourcePath)) {
    Write-Error "Source not found"
    if ($PassThru) { return $false }  # Exits with code 0!
    exit 1  # Never reached
}
```

### Correct Pattern

```powershell
# CORRECT - exit directly with explicit code
if (-not (Test-Path $SourcePath)) {
    Write-Error "Source not found"
    exit 1  # Always exits with explicit code
}
```

## Skill-Integration-Contract-001: Cross-Language Exit Code Contract

**Statement**: Document bash-PowerShell exit code contract: 0 is success, non-zero failure.

**Atomicity**: 88%

### Documentation Template

```powershell
<#
.NOTES
    EXIT CODES (Bash Integration Contract):
    0  - Success: Operation completed successfully
    1  - Error: Source file not found
    1  - Error: Invalid JSON in source
    1  - Error: Missing required key
    1  - Error: Security violation (symlink detected)

    When called from bash:
    - Exit code 0 = success (bash `$?` equals 0)
    - Exit code non-zero = failure (bash `$?` non-zero)
#>
```

### Bash Caller Pattern

```bash
# Check exit code after calling PowerShell
if pwsh -NoProfile -File "$SCRIPT" -PassThru 2>&1; then
    echo "Script succeeded"
else
    echo "Script failed with exit code $?"
fi
```

## Related

- [bash-integration-exit-code-testing](bash-integration-exit-code-testing.md)
- [bash-integration-pattern-discovery](bash-integration-pattern-discovery.md)
