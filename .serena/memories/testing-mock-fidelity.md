# Testing: Mock Fidelity and Integration Requirements

**Domain**: Testing Best Practices
**Last Updated**: 2025-12-26
**Source**: PR #402 debugging session

## Critical Insight

**Unit tests with mocks can provide false confidence when mocks diverge from actual API responses.**

## The Problem: Mock-Reality Gap

### What Happened (PR #402)

**Unit tests**: 100% coverage, all passing ✓
**Runtime**: Failed on ALL 15 PRs ✗

**Root cause**: Test mocks didn't match actual GitHub API structure

```powershell
# Test mock (idealized structure)
MergedPRs = @(
    @{
        number = 789  # lowercase (correct)
        title = "feat: add feature X v2"
    }
)

# Test assertion (PascalCase access)
$result[0].Number | Should -Be 789  # PASSED due to hashtable case-insensitivity

# Runtime code (lowercase access, strict object)
Write-Log "PR #$($similar.number)"  # FAILED - property not found
```

### Why Tests Passed But Runtime Failed

1. **Hashtable case-insensitivity**: `@{number=789}` accessible as `.Number` or `.number`
2. **Type validation missing**: Tests checked VALUES not TYPES
3. **No integration tests**: Never validated against real GitHub API

## Requirements for External API Testing

### Requirement 1: Integration Tests (Mandatory)

**All functions calling external APIs MUST have integration tests.**

```powershell
Describe "Get-SimilarPRs Integration Tests" -Tag "Integration" {
    BeforeAll {
        # Skip if not authenticated
        $authenticated = (gh auth status 2>&1) -match "Logged in"
        if (-not $authenticated) {
            Set-ItResult -Skipped -Because "gh CLI not authenticated"
        }
    }

    It "Returns real API response with correct structure" {
        # Call REAL API (rate-limited, real credentials)
        $result = Get-SimilarPRs -Owner "test-org" -Repo "test-repo" -PRNumber 1 -Title "test"

        # Validate structure matches expectations
        $result | Should -BeOfType [System.Object[]]
        if ($result.Count -gt 0) {
            $result[0] | Should -BeOfType [PSCustomObject]
            $result[0].PSObject.Properties.Name | Should -Contain 'number'
            $result[0].PSObject.Properties.Name | Should -Contain 'title'
            $result[0].number | Should -BeOfType [int]
        }
    }
}
```

### Requirement 2: Type Assertions (Mandatory)

**Unit tests must validate returned TYPES not just VALUES.**

```powershell
It "Returns array of PSCustomObject with lowercase properties" {
    Mock gh {
        return ($Script:Fixtures.MergedPRs | ConvertTo-Json)
    }

    $result = Get-SimilarPRs -Owner "test" -Repo "repo" -PRNumber 123 -Title "test"

    # Type assertions (REQUIRED)
    $result | Should -BeOfType [System.Object[]]
    $result[0] | Should -BeOfType [PSCustomObject]

    # Property name assertions (catch casing issues)
    $result[0].PSObject.Properties.Name | Should -Contain 'number'  # lowercase
    $result[0].PSObject.Properties.Name | Should -Not -Contain 'Number'  # reject PascalCase

    # Value assertions (existing)
    $result[0].number | Should -Be 789
}
```

### Requirement 3: Mock Validation (Recommended)

**Validate mocks against real API responses.**

```powershell
# One-time: Capture real API response
Describe "API Response Capture" -Tag "Capture" {
    It "Captures real GitHub API response structure" {
        $realResponse = gh pr list --repo "owner/repo" --state merged --limit 1 --json number,title | ConvertFrom-Json
        $realResponse | ConvertTo-Json | Out-File "tests/fixtures/github-pr-list-response.json"
    }
}

# Continuous: Validate mocks match captured response
Describe "Mock Fidelity Validation" -Tag "Unit" {
    It "Mock structure matches real API response" {
        $realFixture = Get-Content "tests/fixtures/github-pr-list-response.json" | ConvertFrom-Json
        $mockFixture = $Script:Fixtures.MergedPRs

        # Validate property names match (including casing)
        $realProps = $realFixture[0].PSObject.Properties.Name | Sort-Object
        $mockProps = ($mockFixture[0] | ConvertTo-Json | ConvertFrom-Json).PSObject.Properties.Name | Sort-Object

        $mockProps | Should -Be $realProps -Because "Mock must match real API structure exactly"
    }
}
```

## Contract Testing Pattern

### Step 1: Record Real Response

```bash
# Manual or CI-based capture
gh pr list --repo "owner/repo" --state merged --limit 5 --json number,title,state,author > tests/fixtures/pr-list-merged.json
```

### Step 2: Load as Fixture

```powershell
BeforeAll {
    $Script:RealAPIStructure = Get-Content "tests/fixtures/pr-list-merged.json" | ConvertFrom-Json
}
```

### Step 3: Validate Mocks

```powershell
It "Test fixtures match real API structure" {
    $fixture = $Script:Fixtures.MergedPRs[0] | ConvertTo-Json | ConvertFrom-Json
    $real = $Script:RealAPIStructure[0]

    # Property names must match exactly
    $fixture.PSObject.Properties.Name | Should -Be $real.PSObject.Properties.Name
}
```

## Testing Pyramid for External APIs

| Layer | % of Tests | Purpose | Example |
|-------|-----------|---------|---------|
| Unit | 70% | Business logic with mocks | Similarity matching algorithm |
| Integration | 20% | Real API validation | GitHub API structure |
| E2E | 10% | Full workflow | PR maintenance end-to-end |

## Checklist: External API Testing

When writing tests for functions that call external APIs:

- [ ] Unit tests validate business logic with mocks
- [ ] Unit tests assert returned object TYPES
- [ ] Unit tests validate property names (including casing)
- [ ] Integration test calls real API (tagged, skippable)
- [ ] Integration test validates response structure
- [ ] Real API response captured as fixture (contract testing)
- [ ] Mock structure validated against fixture

## Skills

### Skill-Testing-003: Integration Test Requirement

**Statement**: Functions calling external APIs require integration tests to validate mock fidelity

**Atomicity**: 92%

**Evidence**: PR #402 - Get-SimilarPRs had 100% unit coverage but 0 integration tests. Unit mocks used PascalCase, API returned lowercase. All 15 production runs failed.

### Skill-Testing-006: Mock Structure Fidelity

**Statement**: Test mocks must match actual API response structure including property name casing

**Atomicity**: 93%

**Evidence**: PR #402 - test fixture used lowercase `number` but assertion used PascalCase `.Number`. Passed due to hashtable case-insensitivity but runtime code with strict objects failed.

### Skill-Testing-004: Type Assertions

**Statement**: Unit tests should assert returned object types not just property values

**Atomicity**: 90%

**Evidence**: PR #402 - tests validated `$result[0].Number | Should -Be 789` but never asserted type. Runtime revealed `System.Object[]` (double-nested array) instead of PSCustomObject.

## Related

- **powershell-array-handling.md**: Root cause of PR #402 type mismatch
- **Skill-Testing-001**: Basic testing principles
- **pester-test-isolation.md**: Test independence

## Related

- [testing-002-test-first-development](testing-002-test-first-development.md)
- [testing-003-script-execution-isolation](testing-003-script-execution-isolation.md)
- [testing-004-coverage-pragmatism](testing-004-coverage-pragmatism.md)
- [testing-007-contract-testing](testing-007-contract-testing.md)
- [testing-008-entry-point-isolation](testing-008-entry-point-isolation.md)
