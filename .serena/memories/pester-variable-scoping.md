# Pester Variable Scoping: Use $script: for Cross-Block Visibility

## Problem

In Session 100, a Pester test file triggered PSScriptAnalyzer warning:
> "The variable 'scriptPath' is assigned but never used"

The variable was defined in `BeforeAll` but used in `It` blocks.

## Root Cause

Pester runs each `It` block in its own scope. Variables defined in `BeforeAll` without `$script:` prefix are not visible in `It` blocks.

## Correct Pattern

```powershell
# BeforeAll - use $script: prefix
BeforeAll {
    $script:scriptPath = Join-Path $PSScriptRoot ".." "path" "to" "script.ps1"
    $script:testData = @{ key = "value" }
}

# It blocks - reference with $script: prefix
Describe "MyTests" {
    It "Should find file" {
        Test-Path $script:scriptPath | Should -Be $true
    }
    
    It "Should have test data" {
        $script:testData.key | Should -Be "value"
    }
}
```

## Anti-Pattern

```powershell
# BAD - variable not visible in It blocks
BeforeAll {
    $scriptPath = "..."  # No $script: prefix
}

It "Test" {
    Test-Path $scriptPath  # PSScriptAnalyzer: variable never used
}
```

## Scope Reference

| Block | Scope | Visibility |
|-------|-------|------------|
| `BeforeAll` | Script/Describe | Use `$script:` for cross-block |
| `BeforeEach` | It block | Local to each It |
| `It` | Own scope | Isolated per test |

## Source

- Session 100 (2025-12-29)
- File: tests/Detect-CopilotFollowUpPR.Tests.ps1
- PSScriptAnalyzer rule: PSUseDeclaredVarsMoreThanAssignments
