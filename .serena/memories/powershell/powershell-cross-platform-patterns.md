# PowerShell Cross-Platform Patterns

## Context

**Source**: PR #894 - Installation script fixes
**Date**: 2026-01-13
**Found by**: @bcull during verification testing

## Pattern 1: Temp Directory Path

### Issue

`$env:TEMP` is Windows-only. Linux and macOS do not have this environment variable, causing remote installations to fail.

### Solution

Use `[System.IO.Path]::GetTempPath()` for cross-platform compatibility.

```powershell
# ❌ WRONG (Windows-only)
$TempDir = Join-Path $env:TEMP "ai-agents-install"

# ✅ CORRECT (cross-platform)
$TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "ai-agents-install"
```

### Evidence

- PR #894, commit b4b5ce9
- @bcull: Installation failed on Linux during iex invocation
- Root cause: `$env:TEMP` returned null on Linux

### Related

- `[System.IO.Path]::GetTempPath()` works on Windows, Linux, macOS
- Respects platform temp directory conventions
- No environment variable dependency

## Pattern 2: Glob-to-Regex Conversion Order

### Issue

When converting glob patterns (like `*.agent.md`) to regex, the ORDER of replacements matters. Escaping dots AFTER converting asterisks corrupts the `.*` pattern.

### Root Cause

```powershell
# ❌ WRONG ORDER: Escape dots AFTER asterisks
$Pattern = "*.agent.md"
$Regex = $Pattern -replace "\*", ".*" -replace "\.", "\."
# Result: *.agent.md → .*agent.md → \.*\.agent\.md
# Matches: zero or more DOTS, not any characters

# ✅ CORRECT ORDER: Escape dots FIRST, then asterisks
$Regex = $Pattern -replace "\.", "\." -replace "\*", ".*"
# Result: *.agent.md → *\.agent\.md → .*\.agent\.md
# Matches: any characters followed by .agent.md
```

### Solution

Always escape literal characters (dots, brackets, parentheses) BEFORE converting wildcards (asterisks, question marks).

```powershell
function Convert-GlobToRegex {
    param([string]$Pattern)
    
    # Escape literal characters first
    $Pattern = $Pattern -replace "\.", "\."
    $Pattern = $Pattern -replace "\(", "\("
    $Pattern = $Pattern -replace "\)", "\)"
    $Pattern = $Pattern -replace "\[", "\["
    $Pattern = $Pattern -replace "\]", "\]"
    
    # Then convert wildcards
    $Pattern = $Pattern -replace "\*", ".*"
    $Pattern = $Pattern -replace "\?", "."
    
    return "^$Pattern$"
}
```

### Evidence

- PR #894, commit b851277 (fix), commit 3033a79 (initial attempt)
- Line 250: `$PatternRegex = "^" + ($Config.FilePattern -replace "\.", "\." -replace "\*", ".*") + "$"`
- @bcull: Remote installation via iex failed to find agent files (404 Not Found)
- 20 new tests added to prevent regression (commit 60fb3ae)

### Test Coverage

```powershell
# Regression test: Verify conversion order
$Pattern = "*.agent.md"
$Regex = $Pattern -replace "\.", "\." -replace "\*", ".*"
$Regex | Should -Be ".*\.agent\.md"

# Test actual file matching
"orchestrator.agent.md" -match $Regex | Should -Be $true
"README.md" -match $Regex | Should -Be $false
```

## Pattern 3: Remote Execution Detection

### Context

PowerShell scripts may be invoked locally (with file on disk) or remotely (via `iex` with web content).

### Detection

```powershell
# $PSScriptRoot is set when script is on disk
# $PSScriptRoot is NOT set when script is piped to iex
$IsRemoteExecution = -not $PSScriptRoot
```

### Implications

Remote execution requires different code paths:
- Must download dependencies from web
- Must create temp directory for staging
- Must clean up temp directory on exit/error
- Cannot rely on relative paths

### Evidence

- PR #894: Bugs in remote execution path (lines 198, 250) missed by tests
- Tests ran locally: `$PSScriptRoot` always set → `$IsRemoteExecution = $false`
- User ran via iex: `$PSScriptRoot` not set → `$IsRemoteExecution = $true`
- Coverage gap: 0% of remote path tested initially

### Testing Strategy

Simulate remote execution by clearing `$PSScriptRoot`:

```powershell
Describe "Remote Execution" {
    It "Should download dependencies when PSScriptRoot not set" {
        # Simulate iex invocation
        $script = Get-Content ./install.ps1 -Raw
        $script = $script -replace '\$PSScriptRoot', '$null'
        
        # Execute and verify remote path
        { Invoke-Expression $script } | Should -Not -Throw
    }
}
```

## Integration Points

**Testing Protocol:** Require tests for BOTH local and remote execution paths
**Installation Scripts:** Use `[System.IO.Path]::GetTempPath()` for temp directories
**File Matching:** Escape dots before converting asterisks in glob-to-regex
**Coverage Requirements:** Conditional branches like `if ($IsRemoteExecution)` require tests for EACH path

## Related Patterns

- `.serena/memories/testing-coverage-requirements.md` - Coverage protocol
- `.agents/retrospective/2026-01-13-pr894-test-coverage-failure.md` - Full incident analysis
- Issue #892, PR #894 - Source incidents
