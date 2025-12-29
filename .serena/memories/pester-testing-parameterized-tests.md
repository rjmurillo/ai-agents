# Skill-Test-Pester-002: -ForEach Migration Pattern

**Statement**: Replace foreach loops with -ForEach parameter on It blocks for Pester 5.x parameterized tests.

**Context**: When migrating from Pester 4.x or using parameterized tests.

**Evidence**: Tests using -ForEach @(...) { $_.Param } pattern succeeded.

**Atomicity**: 94%

## Problem

```powershell
# WRONG - Traditional foreach not compatible with Pester 5.x
Describe "Config" {
    $environments = @("Claude", "Copilot", "VSCode")

    foreach ($env in $environments) {
        It "should have $env config" {
            $config[$env] | Should -Not -BeNullOrEmpty
        }
    }
}
```

## Solution

```powershell
# CORRECT - Use -ForEach parameter
Describe "Config" {
    It "should have <Env> config" -ForEach @(
        @{ Env = "Claude" }
        @{ Env = "Copilot" }
        @{ Env = "VSCode" }
    ) {
        $config[$Env] | Should -Not -BeNullOrEmpty
    }
}
```

## Key Points

- Use `<ParamName>` in test name for dynamic naming
- Each hashtable is one test case
- Variables accessible directly (`$Env` not `$_.Env`)
