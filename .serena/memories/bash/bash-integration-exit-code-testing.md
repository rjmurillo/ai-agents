# Skill-Testing-Integration-001: Exit Code Contract Testing

**Statement**: Test PowerShell script exit codes with `$LASTEXITCODE` assertions when called from bash.

**Context**: When writing Pester tests for PowerShell scripts invoked from bash hooks.

**Evidence**: PR #52 Bug 2 - Exit code 0 vs non-zero not tested, allowing bug to pass.

**Atomicity**: 90%

## Test Pattern

```powershell
Describe "Exit Codes" {
    It "Returns non-zero on source not found" {
        # Use & operator to invoke script
        & $scriptPath -SourcePath "nonexistent.json" 2>&1 | Out-Null
        $LASTEXITCODE | Should -Not -Be 0
    }

    It "Returns non-zero on invalid JSON" {
        & $scriptPath -SourcePath $invalidJsonPath 2>&1 | Out-Null
        $LASTEXITCODE | Should -Not -Be 0
    }

    It "Returns 0 on success" {
        & $scriptPath -SourcePath $validSourcePath
        $LASTEXITCODE | Should -Be 0
    }
}
```

## Key Points

- Use `&` operator (call operator) to invoke scripts for proper exit code capture
- Redirect stderr with `2>&1 | Out-Null` to suppress error output in tests
- Test BOTH success (0) and failure (non-zero) paths
- Add to every PowerShell script that will be called from bash

## Related

- [bash-integration-exit-codes](bash-integration-exit-codes.md)
- [bash-integration-pattern-discovery](bash-integration-pattern-discovery.md)
