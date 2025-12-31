---
name: Testing Approach
applyTo: "**/*.Tests.ps1"
priority: 7
version: 1.0.0
status: active
---

# Testing Approach Steering

This steering file provides Pester 5.x testing conventions and patterns used in this repository.

## Scope

**Applies to**: `**/*.Tests.ps1` - Pester test files

## Guidelines

### Test File Structure

Every test file MUST:

1. Start with `#Requires -Modules Pester`
2. Include comment-based help (`.SYNOPSIS`, `.DESCRIPTION`, `.NOTES`)
3. Use `BeforeAll` for script loading and shared setup
4. Organize tests with `Describe` > `Context` > `It` hierarchy

```powershell
#Requires -Modules Pester

<#
.SYNOPSIS
    Tests for [Script-Name].ps1

.DESCRIPTION
    Validates [description of what is tested]

.NOTES
    Test Approach: [Explain testing strategy used]
#>

BeforeAll {
    $repoRoot = Join-Path $PSScriptRoot ".."
    $ScriptPath = Join-Path $repoRoot "[path]" "[Script-Name].ps1"
    $scriptContent = Get-Content $ScriptPath -Raw
}

Describe "[Script-Name]" {
    Context "[Feature Area]" {
        It "Should [expected behavior]" {
            # Test implementation
        }
    }
}
```

### Testing Strategies

This repository uses two complementary approaches:

#### Pattern-Based Tests (Structural Validation)

Validate code structure by matching regex patterns in script content:

```powershell
Context "Parameter Definitions" {
    It "Has PullRequest as mandatory parameter" {
        $scriptContent | Should -Match '\[Parameter\(Mandatory\)\]\s*\[int\]\$PullRequest'
    }

    It "Should have CmdletBinding attribute" {
        $scriptContent | Should -Match '\[CmdletBinding\(\)\]'
    }

    It "Should set ErrorActionPreference to Stop" {
        $scriptContent | Should -Match '\$ErrorActionPreference\s*=\s*"Stop"'
    }
}
```

**When to use**: Verify required elements exist (parameters, imports, functions, documentation).

#### Functional Tests (Behavioral Validation)

Test actual function behavior with mock data following AAA pattern:

```powershell
Context "Behavior Tests" {
    BeforeAll {
        # ARRANGE - Set up test data
        $testData = @{
            number = 123
            title = "Test PR"
            state = "OPEN"
        }
    }

    It "Should return correct structure" {
        # ACT
        $result = Get-Something -Data $testData

        # ASSERT
        $result.Success | Should -BeTrue
        $result.Number | Should -Be 123
    }
}
```

### Pester 5.x Conventions

#### Parameterized Tests with -ForEach

Use `-ForEach` parameter instead of traditional `foreach` loops:

```powershell
# CORRECT - Use -ForEach parameter
It "should have <Env> config" -ForEach @(
    @{ Env = "Claude" }
    @{ Env = "Copilot" }
    @{ Env = "VSCode" }
) {
    $config[$Env] | Should -Not -BeNullOrEmpty
}

# WRONG - Traditional foreach (Pester 4.x style)
foreach ($env in @("Claude", "Copilot", "VSCode")) {
    It "should have $env config" {
        $config[$env] | Should -Not -BeNullOrEmpty
    }
}
```

#### BeforeAll vs BeforeEach

- **BeforeAll**: Runs once before all tests in the scope (expensive setup)
- **BeforeEach**: Runs before each test (isolation setup)

```powershell
Describe "Tests" {
    BeforeAll {
        # One-time expensive setup
        $scriptContent = Get-Content $ScriptPath -Raw
    }

    Context "File-Based Tests" {
        BeforeEach {
            # Clean test directory before EACH test for isolation
            Get-ChildItem -Path $TestDir -Recurse |
                Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
        }

        It "Test 1" {
            Set-Content -Path "$TestDir\file1.md" -Value "..."
        }

        It "Test 2" {
            # Isolated - doesn't see file1.md from Test 1
            Set-Content -Path "$TestDir\file2.md" -Value "..."
        }
    }
}
```

### Test Isolation Requirements

Every `Context` block creating files MUST have `BeforeEach` cleanup:

```powershell
Context "Pattern Tests" {
    BeforeEach {
        # Clean test directory before EACH test
        Get-ChildItem -Path $TestDir -Recurse |
            Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
    }

    It "Test creates file" {
        Set-Content -Path "$TestDir\file.md" -Value "content"
        (Get-ChildItem $TestDir).Count | Should -Be 1  # PASSES - isolated
    }
}
```

### Cross-Platform Path Assertions

Use regex with alternation `[\\/]` for path assertions:

```powershell
# CORRECT - Flexible path matching
It "should resolve path" {
    $result | Should -Match "MyRepo[\\/]\.github[\\/]agents"
}

# WRONG - Hardcoded path separator
It "should resolve path" {
    $result | Should -Be "C:\MyRepo\.github\agents"  # Fails on Unix
}
```

### Contract Testing for API Mocks

Mock data structures MUST match real API response schemas:

```powershell
# GOOD - Matches GitHub API casing (lowercase)
$mockPR = @{ number = 123; title = "Test PR"; state = "OPEN" }

# BAD - Wrong casing (masked by PowerShell case-insensitivity)
$mockPR = @{ Number = 123; Title = "Test PR"; State = "OPEN" }
```

Validate structure with type assertions:

```powershell
It "returns array of PSCustomObject, not nested array" {
    $result = Get-SimilarPRs -Owner "test" -Repo "repo" -PR 123

    # Assert type
    $result | Should -BeOfType [System.Object[]]

    # Assert NOT double-nested
    $result[0] | Should -Not -BeOfType [System.Object[]]

    # Assert properties exist
    $result[0].number | Should -Be 123
}
```

## Patterns

### Comment-Based Help Testing

```powershell
Context "Comment-Based Help" {
    BeforeAll {
        $scriptContent = Get-Content $ScriptPath -Raw
    }

    It "Should have .SYNOPSIS section" {
        $scriptContent | Should -Match '\.SYNOPSIS'
    }

    It "Should have .DESCRIPTION section" {
        $scriptContent | Should -Match '\.DESCRIPTION'
    }

    It "Should have .PARAMETER sections" {
        $scriptContent | Should -Match '\.PARAMETER Owner'
    }

    It "Should have .EXAMPLE sections" {
        $scriptContent | Should -Match '\.EXAMPLE'
    }
}
```

### GraphQL Query Structure Testing

```powershell
Context "GraphQL Query Structure" {
    It "Should use parameterized GraphQL query" {
        $scriptContent | Should -Match 'query\(\$owner:\s*String!,\s*\$repo:\s*String!,\s*\$prNumber:\s*Int!\)'
    }

    It "Should use gh api graphql command" {
        $scriptContent | Should -Match 'gh api graphql'
    }

    It "Should pass parameters with -f and -F flags" {
        $scriptContent | Should -Match '-f owner='
        $scriptContent | Should -Match '-F prNumber='
    }

    It "Should not use PowerShell interpolation in query" {
        # Verify here-string with single quotes (no interpolation)
        $scriptContent | Should -Match '\$query\s*=\s*@'''
    }
}
```

### Error Handling Testing

```powershell
Context "Error Handling" {
    It "Should check LASTEXITCODE after gh api command" {
        $scriptContent | Should -Match '\$LASTEXITCODE -ne 0'
    }

    It "Should capture stderr with 2>&1" {
        $scriptContent | Should -Match 'gh api graphql.*2>&1'
    }

    It "Should use try-catch for JSON parsing" {
        $scriptContent | Should -Match 'try\s*\{'
        $scriptContent | Should -Match 'catch\s*\{'
    }
}
```

### Exit Code Testing

```powershell
Context "Exit Code Logic" {
    It "Should document exit codes in help" {
        $scriptContent | Should -Match 'Exit Codes:'
        $scriptContent | Should -Match '0:\s*PR is NOT merged'
        $scriptContent | Should -Match '1:\s*PR IS merged'
        $scriptContent | Should -Match '2:\s*Error occurred'
    }

    It "Should exit with code 0 when not merged" {
        $scriptContent | Should -Match 'exit\s+0'
    }

    It "Should exit with code 1 when merged" {
        $scriptContent | Should -Match 'exit\s+1'
    }
}
```

## Anti-Patterns

### Test Interdependencies

```powershell
# WRONG - Test 2 depends on Test 1 state
Context "Tests" {
    It "Test 1 creates data" {
        $script:SharedData = "created"  # Side effect
    }

    It "Test 2 uses data" {
        $script:SharedData | Should -Be "created"  # Fails if run alone
    }
}

# CORRECT - Each test is independent
Context "Tests" {
    It "Test 1" {
        $data = "created"
        $data | Should -Be "created"
    }

    It "Test 2" {
        $data = "created"  # Own setup
        $data | Should -Be "created"
    }
}
```

### Missing BeforeEach Cleanup

```powershell
# WRONG - Missing cleanup causes pollution
Context "Pattern Tests" {
    # No BeforeEach!
    It "Test 1" {
        Set-Content "$TestDir\file1.md" -Value "..."
    }
    It "Test 2" {
        # Sees file1.md from Test 1 - POLLUTION
        (Get-ChildItem $TestDir).Count | Should -Be 1  # FAILS - sees 2
    }
}
```

### Idealized Mock Data

```powershell
# WRONG - Mock doesn't match real API
$mock = @{ Number = 123 }  # PascalCase

# CORRECT - Capture schema from real API
$realResponse = gh pr view 123 --json number | ConvertFrom-Json
# Then create mock matching exact casing
$mock = @{ number = 123 }
```

### Assertions Without Type Checks

```powershell
# INCOMPLETE - Only checks value
$result.number | Should -Be 123

# COMPLETE - Checks type AND value
$result | Should -BeOfType [PSCustomObject]
$result.number | Should -Be 123
```

## Coverage Expectations

- Target: ≥80% code coverage for happy paths
- Required coverage areas:
  - All public parameters
  - Main execution paths
  - Error handling branches
  - Exit codes

## References

- [Test-PRMerged.Tests.ps1](/.claude/skills/github/scripts/pr/Test-PRMerged.Tests.ps1) - Comprehensive example
- [Invoke-CopilotAssignment.Tests.ps1](/tests/Invoke-CopilotAssignment.Tests.ps1) - Mixed approach example
- Memory: `pester-testing-test-isolation`
- Memory: `pester-testing-cross-platform`
- Memory: `testing-007-contract-testing`
