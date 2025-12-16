# Pester Test Isolation Pattern

## Context

Testing pattern for ensuring test isolation in Pester test suites, particularly for file-based tests.

## Pattern

### Three-Level Isolation Strategy

1. **Session-level**: `BeforeAll` creates isolated temp directory
2. **Test-level**: `BeforeEach` cleans temp directory before each test
3. **Session cleanup**: `AfterAll` removes temp directory

### Implementation Example

```powershell
BeforeAll {
    # Create isolated temp directory per test run
    $Script:TestTempDir = Join-Path $env:TEMP "TestName-$(Get-Random)"
    New-Item -ItemType Directory -Path $Script:TestTempDir -Force | Out-Null
}

AfterAll {
    # Cleanup after all tests
    if (Test-Path $Script:TestTempDir) {
        Remove-Item -Path $Script:TestTempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Context "Feature Tests" {
    BeforeEach {
        # Clean test directory before EACH test
        Get-ChildItem -Path $Script:TestTempDir -Recurse | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
    }
    
    It "Test 1" { ... }
    It "Test 2" { ... }
}
```

## Key Lessons

### Bug Prevention

- **Always include BeforeEach cleanup** in every Context block that creates files
- Missing BeforeEach causes test pollution where tests see artifacts from previous tests
- File count assertions are sensitive indicators of pollution

### Regression Coverage

- Multiple tests in same context implicitly verify cleanup works
- Tests with exact file count assertions (e.g., "Files to scan: 1") detect pollution
- No need for explicit "test isolation" meta-tests

### Pattern Consistency

- Use identical cleanup pattern across all Context blocks
- Makes code reviewable and maintainable
- Reduces chance of missing cleanup in new contexts

## Real-World Example

From `Validate-PathNormalization.Tests.ps1` (PR #47):

- 5 contexts, each with BeforeEach cleanup
- Tests create files with different names
- File count assertions would fail if cleanup missing
- Detected via CodeRabbit review when "Pattern Detection" context was missing BeforeEach

## Anti-Pattern

```powershell
Context "Tests" {
    # MISSING BeforeEach - WRONG!
    
    It "Test 1" { 
        Set-Content -Path "$TestDir\file1.md" -Value "..."
    }
    It "Test 2" {
        Set-Content -Path "$TestDir\file2.md" -Value "..."
        # This test now sees file1.md from Test 1!
    }
}
```

## Verification

Test isolation is working when:

1. All tests pass individually and together
2. Test order doesn't matter
3. File count assertions match expected values
4. Tests can be run multiple times with same results
