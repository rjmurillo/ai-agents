# Skill-Test-Pester-004: BeforeEach Cleanup for Test Isolation

**Statement**: Every Pester Context block creating files needs BeforeEach cleanup to prevent test pollution.

**Context**: When writing file-based Pester tests with multiple It blocks.

**Evidence**: PR #47 - Pattern Detection context missing BeforeEach caused cross-test file accumulation.

**Atomicity**: 96%

**Impact**: 9/10

## Problem

```powershell
# WRONG - Missing BeforeEach causes test pollution
Context "Pattern Tests" {
    # No BeforeEach cleanup!

    It "Test 1" {
        Set-Content -Path "$TestDir\file1.md" -Value "..."
    }

    It "Test 2" {
        Set-Content -Path "$TestDir\file2.md" -Value "..."
        # This test now sees file1.md from Test 1!
        (Get-ChildItem $TestDir).Count | Should -Be 1  # FAILS - sees 2 files
    }
}
```

## Solution

```powershell
# CORRECT - BeforeEach cleanup ensures isolation
Context "Pattern Tests" {
    BeforeEach {
        # Clean test directory before EACH test
        Get-ChildItem -Path $TestDir -Recurse | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
    }

    It "Test 1" {
        Set-Content -Path "$TestDir\file1.md" -Value "..."
        (Get-ChildItem $TestDir).Count | Should -Be 1  # PASSES
    }

    It "Test 2" {
        Set-Content -Path "$TestDir\file2.md" -Value "..."
        (Get-ChildItem $TestDir).Count | Should -Be 1  # PASSES - isolated
    }
}
```
