# Skill-Test-Pester-001: Discovery Phase Pattern

**Statement**: Pester 5.x evaluates code outside BeforeAll during Discovery; use BeforeAll for all variable initialization.

**Context**: When writing Pester 5.x tests with shared variables.

**Evidence**: 42 test failures in ai-agents until variables moved to BeforeAll.

**Atomicity**: 96%

## Problem

```powershell
# WRONG - Variables assigned during Discovery phase
Describe "Test" {
    $Script:TestDir = Join-Path $env:TEMP "test"  # Evaluated during Discovery!

    It "should work" {
        Test-Path $Script:TestDir | Should -Be $true
    }
}
```

## Solution

```powershell
# CORRECT - Variables assigned in BeforeAll
Describe "Test" {
    BeforeAll {
        $Script:TestDir = Join-Path $env:TEMP "test-$(Get-Random)"
        New-Item -ItemType Directory -Path $Script:TestDir -Force | Out-Null
    }

    AfterAll {
        Remove-Item -Path $Script:TestDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    It "should work" {
        Test-Path $Script:TestDir | Should -Be $true
    }
}
```

## Related

- [pester-cross-platform](pester-cross-platform.md)
- [pester-parameterized-tests](pester-parameterized-tests.md)
- [pester-test-first](pester-test-first.md)
- [pester-test-isolation-pattern](pester-test-isolation-pattern.md)
- [pester-test-isolation](pester-test-isolation.md)
