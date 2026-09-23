# QA Assessment: PR-55 Wildcard Detection Bug Fix

**Date**: 2025-12-17
**QA Agent**: qa
**Fix Location**: `build/scripts/Invoke-PesterTests.ps1:111`
**Commit**: 106d211

## Executive Summary

**Regression Test Recommendation**: YES - CRITICAL
**Priority**: Major
**Estimated Effort**: 2-3 hours (test design + implementation)

## Bug Analysis

### The Bug

**Before (BROKEN)**:
```powershell
if ($fullPath -like "*[*]*" -or $fullPath -like "*?*") {
```

**After (FIXED)**:
```powershell
if ($fullPath -like "*[*]*" -or $fullPath -like "*[?]*") {
```

### Root Cause

PowerShell's `-like` operator treats `?` as a wildcard that matches ANY single character. The condition `$fullPath -like "*?*"` matches ANY path with at least 2 characters (the `?` matches any single character between the two `*` wildcards).

This meant:
- `"C:\temp\file.txt"` matched (TRUE) → took wildcard expansion branch incorrectly
- `"C:\temp\test?.ps1"` matched (TRUE) → correct branch but for wrong reason
- The elseif branch for `Test-Path` was DEAD CODE for all paths with 2+ characters

### Impact Classification

- **Severity**: High - core path resolution logic was broken
- **Scope**: All paths with 2+ characters incorrectly took wildcard expansion branch
- **Detection**: Subtle - Get-Item silently failed for non-wildcard paths, fallback worked by accident
- **User Impact**: Low actual impact (Get-Item fails gracefully), but logic is fundamentally wrong

## Regression Test Coverage

### Test Strategy

Create comprehensive regression tests for `Invoke-PesterTests.ps1` covering:

1. **Wildcard vs Literal Character Detection** (Critical)
2. **Path Resolution Correctness** (High)
3. **Edge Cases** (Medium)

### Required Test Cases

#### Critical: Wildcard Character Detection

| Test Case | Path Example | Expected Branch | Rationale |
|-----------|--------------|-----------------|-----------|
| Literal `?` character | `test?.Tests.ps1` | Wildcard expansion | `?` should be treated as wildcard |
| Literal `*` character | `test[*].ps1` | Wildcard expansion | Escaped `*` in filename |
| Path with `?` wildcard | `test?.ps1` | Wildcard expansion | Single char wildcard |
| Path with `*` wildcard | `*.Tests.ps1` | Wildcard expansion | Multi char wildcard |
| No wildcards | `Specific.Tests.ps1` | Test-Path branch | Normal file path |

#### High: Path Resolution Correctness

| Test Case | Input | Expected Behavior |
|-----------|-------|-------------------|
| Relative path with wildcard | `./tests/*.ps1` | Expands to absolute paths |
| Absolute path with wildcard | `C:\tests\*.ps1` | Expands to multiple files |
| Relative path without wildcard | `./tests/Specific.Tests.ps1` | Resolves to absolute path |
| Non-existent wildcard path | `./tests/nonexistent*.ps1` | Returns empty (no match) |
| Non-existent specific path | `./tests/nonexistent.ps1` | Returns empty (no match) |

#### Medium: Edge Cases

| Test Case | Scenario | Expected Result |
|-----------|----------|-----------------|
| Path with both `*` and `?` | `test*?.ps1` | Wildcard expansion |
| Empty path array | `@()` | No crash, empty result |
| Path with special chars | `test[abc].ps1` | Handled correctly |

### Test File Structure

```powershell
# build/scripts/tests/Invoke-PesterTests.Tests.ps1

BeforeAll {
    $Script:TestTempDir = Join-Path $env:TEMP "Invoke-PesterTests-$(Get-Random)"
    New-Item -ItemType Directory -Path $Script:TestTempDir -Force | Out-Null
    $Script:RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    $Script:ScriptPath = Join-Path $Script:RepoRoot "build\scripts\Invoke-PesterTests.ps1"
}

AfterAll {
    if (Test-Path $Script:TestTempDir) {
        Remove-Item -Path $Script:TestTempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Describe "Invoke-PesterTests Wildcard Detection" {

    Context "Wildcard Character Escaping" {
        BeforeEach {
            Get-ChildItem -Path $Script:TestTempDir -Recurse | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
        }

        It "Should expand path with literal ? wildcard" {
            # Create test files: test1.ps1, test2.ps1
            # Test pattern: test?.ps1
            # Expected: Both files found via wildcard expansion
        }

        It "Should expand path with literal * wildcard" {
            # Test pattern: *.Tests.ps1
            # Expected: All matching files via expansion
        }

        It "Should NOT expand path without wildcards" {
            # Create: Specific.Tests.ps1
            # Test pattern: Specific.Tests.ps1
            # Expected: Uses Test-Path branch, not wildcard expansion
        }
    }

    Context "Path Resolution" {
        It "Should resolve relative paths correctly" { }
        It "Should handle non-existent wildcard paths" { }
        It "Should handle non-existent specific paths" { }
    }
}
```

## Why This Test Matters

### Regression Prevention

The bug was **extremely subtle**:
- PowerShell wildcard semantics are non-obvious
- The incorrect code appeared to work (Get-Item failed gracefully)
- No tests existed to catch this during development

### Pattern Validation

From `powershell-testing-patterns` memory:
- PowerShell logic errors like this require edge case coverage
- String/pattern matching operators need explicit validation
- Dead code branches indicate missing test coverage

### Skill Application

This applies **Skill-PowerShell-Testing-Process-001**:
- Write tests BEFORE implementation (or immediately after bugs)
- Tests surface edge cases that manual testing misses
- Parameter combination tests catch subtle logic errors

## Implementation Notes

### Testing Approach

1. **Isolation**: Use Pester test isolation pattern (BeforeAll/AfterAll/BeforeEach)
2. **Verification**: Create actual test files with wildcard-like names
3. **Assertion**: Verify correct branch taken (wildcard vs Test-Path)

### Verification Method

The test cannot directly observe which branch executes, but can verify outcomes:

```powershell
# Setup: Create test1.ps1, test2.ps1
$result = & $ScriptPath -TestPath "test?.ps1" -OutputPath "./output"

# Verify: Both files found (proves wildcard expansion worked)
$result | Should -HaveCount 2
```

### Test Complexity

- **Medium complexity**: Requires file system setup
- **High value**: Catches subtle PowerShell semantics bugs
- **Maintainable**: Follows existing test pattern in `build/scripts/tests/`

## Test Quality Metrics

| Metric | Target | Rationale |
|--------|--------|-----------|
| Branch Coverage | 100% | Must cover both wildcard and Test-Path branches |
| Edge Case Coverage | 80%+ | Wildcard chars, empty paths, special chars |
| Regression Coverage | 100% | Must catch the exact bug that occurred |
| Execution Time | <5 sec | File-based tests, keep lean |

## Recommendation Summary

**CREATE REGRESSION TEST**: YES

**Rationale**:
1. **Bug Severity**: High - core logic was broken
2. **Subtlety**: Extremely subtle PowerShell semantics
3. **Dead Code**: Elseif branch was unreachable
4. **No Coverage**: No tests exist for `Invoke-PesterTests.ps1`
5. **Reoccurrence Risk**: High - easy to reintroduce during refactoring

**Priority**: **Major** (not Critical because actual impact was low, but logic flaw was severe)

**Test Scope**:
- 5-8 core test cases
- Focus on wildcard detection logic (lines 111-120)
- Include path resolution verification
- Follow Pester isolation pattern

**Expected Outcome**:
- Prevents regression of this specific bug
- Validates wildcard escaping works correctly
- Provides confidence for future refactoring
- Documents expected behavior for maintainers

## Next Steps

1. Implementer creates `build/scripts/tests/Invoke-PesterTests.Tests.ps1`
2. Implement test cases from "Required Test Cases" section
3. Run tests: `pwsh build/scripts/Invoke-PesterTests.ps1 -TestPath "./build/scripts/tests/Invoke-PesterTests.Tests.ps1"`
4. Verify all tests pass
5. Add to CI pipeline

## Status

**QA ASSESSMENT COMPLETE**

**Handoff**: Return to orchestrator with recommendation to route to implementer for test creation.
