# CodeQL Verification Fixes - Session 382

**Date**: 2026-01-16  
**Session**: 382  
**Branch**: feat/codeql  
**Commits**: 18eecaef

## Summary

Implemented four verification comments from PR review to fix CodeQL quick scan, config, timeout, and diagnostics issues.

## Key Learnings

### 1. Machine-Readable Output Parsing

**Problem**: Hook regex parsing `'Found (\d+) findings'` didn't match console output format  
**Solution**: Use `-Format json` instead of `-Format console` for structured parsing  
**Pattern**: Always prefer machine-readable formats (JSON, SARIF) for automated parsing over console text

**Example**:
```powershell
# WRONG: Parse console output with regex
& $ScanScript -Format console 2>&1
if ($scanOutput -match 'Found (\d+) findings') { ... }

# CORRECT: Use JSON format
& $ScanScript -Format json 2>&1
$scanResult = $jsonOutput | ConvertFrom-Json
$findingsCount = $scanResult.TotalFindings
```

### 2. Strict CWE Scoping for Quick Scans

**Problem**: Quick scan config included extra CWEs (CWE-020, CWE-611) beyond requested critical list  
**Impact**: Longer scan times, exceeded 30-second budget, intent mismatch  
**Solution**: Strictly limit to requested CWEs: 078 (command injection), 079 (XSS), 089 (SQLi), 022 (path traversal), 798 (hardcoded credentials)

**Learning**: Quick scan configs must balance coverage vs performance - only critical, high-signal queries

### 3. Timeout Enforcement at All Entry Points

**Problem**: Hook had 30-second timeout, but direct script invocation didn't  
**Solution**: Add timeout handling in `Invoke-CodeQLDatabaseAnalyze` when `-QuickScan` is set  
**Pattern**: Implement constraints at the source, not just at call sites

**Implementation**:
```powershell
if ($QuickScan) {
    $job = Start-Job -ScriptBlock { ... }
    $completed = Wait-Job -Job $job -Timeout 30
    if ($null -eq $completed) {
        # Timeout - return graceful degradation per ADR-035
        return @{ FindingsCount = 0; TimedOut = $true }
    }
}
```

### 4. Cache Validation Logic Consistency

**Problem**: Diagnostics used simplified cache check (git HEAD only), not full validation  
**Solution**: Import comprehensive validation from `Invoke-CodeQLScan.ps1`:
- Git HEAD hash
- Config file hash
- Scripts directory hash (.codeql/scripts/)
- Config directory hash (.github/codeql/)

**Pattern**: Reuse validation logic across scripts, don't create inconsistent stubs

### 5. PSScriptAnalyzer: `Using:` Scope in Start-Job

**Problem**: Variables in Start-Job script blocks need `Using:` scope modifier  
**Fix**: Rename parameters to avoid conflict with automatic variables ($Args)

```powershell
# WRONG
$job = Start-Job -ScriptBlock {
    param($CodeQL, $Args)  # $Args is automatic variable
    & $CodeQL @Args  # PSScriptAnalyzer warnings
}

# CORRECT
$job = Start-Job -ScriptBlock {
    param($CodeQLExe, $AnalysisArgs)
    & $CodeQLExe @AnalysisArgs
}
```

## Files Modified

1. `.claude/hooks/PostToolUse/Invoke-CodeQLQuickScan.ps1` - JSON output parsing
2. `.github/codeql/codeql-config-quick.yml` - Remove extra CWEs
3. `.codeql/scripts/Invoke-CodeQLScan.ps1` - Add QuickScan timeout
4. `.codeql/scripts/Get-CodeQLDiagnostics.ps1` - Replace stub validation

## Related

- ADR-035: Exit code standardization (graceful degradation on timeout)
- bash-integration-exit-codes: Cross-language exit code contract
- patterns-powershell-pitfalls: PSScriptAnalyzer best practices
