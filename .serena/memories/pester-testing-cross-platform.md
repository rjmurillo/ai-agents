# Skill-Test-Pester-003: Cross-Platform Path Assertions

**Statement**: Use regex with alternation ([\\/]) for path assertions in cross-platform PowerShell tests.

**Context**: When tests need to work on both Windows and Unix.

**Evidence**: Path separator mismatches resolved with flexible regex.

**Atomicity**: 90%

## Problem

```powershell
# WRONG - Hardcoded path separator
It "should resolve path" {
    $result | Should -Be "C:\MyRepo\.github\agents"  # Fails on Unix
}
```

## Solution

```powershell
# CORRECT - Flexible path matching
It "should resolve path" {
    # Option 1: Use -Match with flexible separator
    $result | Should -Match "MyRepo[\\/]\.github[\\/]agents"

    # Option 2: Normalize before comparison
    $normalizedResult = $result -replace '[/\\]', [IO.Path]::DirectorySeparatorChar
    $normalizedExpected = "MyRepo/.github/agents" -replace '[/\\]', [IO.Path]::DirectorySeparatorChar
    $normalizedResult | Should -Match [regex]::Escape($normalizedExpected)
}
```

## Pattern: `[\\/]`

Matches both forward slash (`/`) and backslash (`\`) for cross-platform compatibility.

## Related

- [pester-test-isolation-pattern](pester-test-isolation-pattern.md)
- [pester-testing-discovery-phase](pester-testing-discovery-phase.md)
- [pester-testing-parameterized-tests](pester-testing-parameterized-tests.md)
- [pester-testing-test-first](pester-testing-test-first.md)
- [pester-testing-test-isolation](pester-testing-test-isolation.md)
