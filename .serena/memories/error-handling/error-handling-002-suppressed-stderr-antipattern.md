# Error Handling Anti-Pattern: Suppressed stderr/stdout

**Importance**: CRITICAL  
**Date**: 2026-01-16  
**Context**: PR #954 CodeQL Integration CI Failures  
**Related**: security-003-secure-error-handling, error-handling-audit-session-378

## Anti-Pattern

**Problem**: Redirecting external command stderr/stdout to `Write-Verbose` **before** checking exit codes suppresses critical error messages.

```powershell
# WRONG: Error details lost
& $ExternalCommand @Args 2>&1 | Out-String | Write-Verbose
if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code $LASTEXITCODE"  # No context!
}
```

**Impact**:
- CI failures are cryptic ("exit code 2") with no actionable information
- Developers cannot diagnose issues
- Wastes time investigating infrastructure vs code issues

## Correct Pattern

```powershell
# CORRECT: Capture output, show errors on failure, verbose on success
$output = & $ExternalCommand @Args 2>&1

if ($LASTEXITCODE -ne 0) {
    # Show actual error output for troubleshooting
    $errorDetails = ($output | Out-String).Trim()
    if ($errorDetails) {
        Write-Error "Command failed with exit code ${LASTEXITCODE}:`n$errorDetails"
    }
    throw "Command failed with exit code $LASTEXITCODE"
}

# Log verbose output only on success
$output | Out-String | Write-Verbose
```

## When to Use Verbose Logging

**Use `Write-Verbose` for**:
- Successful operation details (not needed unless debugging)
- Progress messages during long operations
- Internal state for troubleshooting

**DO NOT use `Write-Verbose` for**:
- Error messages or diagnostic output from failed external commands
- Validation failures
- Anything needed to understand why an operation failed

## Real-World Example

In `Invoke-CodeQLScan.ps1`, database creation failures were cryptic:
```
CodeQL database creation failed with exit code 2
```

After fix, shows actual CodeQL error:
```
CodeQL database creation failed with exit code 2:
Error: No Python code found in specified paths
Error: Database creation requires at least one source file
```

## Detection

**Code smell**: `2>&1 | ... | Write-Verbose` before `if ($LASTEXITCODE -ne 0)`

**Search pattern**:
```bash
grep -n "2>&1.*Write-Verbose" **/*.ps1
grep -B2 "LASTEXITCODE.*-ne 0" **/*.ps1 | grep -A2 "Write-Verbose"
```

## Related Patterns

- **security-003-secure-error-handling**: Don't expose secrets in errors
- **bash-integration-exit-codes**: Proper exit code usage
- **ci-infrastructure-output-handling**: CI-friendly error reporting
