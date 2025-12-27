# Skill-Testing-007: Contract Testing for API Mocks

**Statement**: Mock data structures must match real API response schemas including property casing

**Atomicity**: 90%

**Context**: When creating test mocks for external APIs, validate structure against real responses

**Evidence**: PR #402 retrospective - Mock-reality gap (PascalCase vs lowercase) caused double-nested array bug

## When to Apply

**Trigger Conditions**:
- Creating test mocks for external API responses
- Adding new API integrations
- Debugging test-pass-but-runtime-fail scenarios
- Updating mocks after API changes

**Applies To**:
- GitHub API mocks (REST and GraphQL)
- Any external API integration
- Unit tests with mocked dependencies
- Integration test fixtures

## How to Apply

1. **Capture Real Response**: Execute API call, save raw JSON
2. **Extract Schema**: Document field names, types, nesting structure
3. **Match Property Casing**: Respect exact casing (lowercase, PascalCase, camelCase)
4. **Validate Structure**: Ensure mocks return same shape as API
5. **Add Type Assertions**: Test that returned type matches expected

## Example (PR #402 Bug)

**Problem**: Unit tests passed, runtime failed with "property 'number' not found"

**Root Cause**:
- **Mock**: Used PascalCase properties (`Number`, `Title`)
- **Real API**: Uses lowercase properties (`number`, `title`)
- **PowerShell**: Hashtables are case-insensitive (masked issue in tests)
- **Runtime**: Accessing `$pr.number` on double-nested array failed

**Solution**:
```powershell
# BAD (mock doesn't match API)
$mockPR = @{ Number = 123; Title = "Test PR" }

# GOOD (matches GitHub API casing)
$mockPR = @{ number = 123; title = "Test PR" }
```

## Schema Validation Pattern

```powershell
# Capture real API response
$realResponse = gh pr view 123 --json number,title,state | ConvertFrom-Json

# Extract schema
$schema = $realResponse | Get-Member -MemberType NoteProperty | 
  Select-Object Name, MemberType, Definition

# Document for mock creation
$schema | Format-Table
# Name   MemberType   Definition
# ----   ----------   ----------
# number NoteProperty int number=123
# title  NoteProperty string title=Test PR
# state  NoteProperty string state=OPEN

# Create mock matching schema
$mock = @{
  number = 123
  title = "Test PR"
  state = "OPEN"
}
```

## Type Assertion Pattern

```powershell
It "returns array of PSCustomObject, not nested array" {
  $result = Get-SimilarPRs -Owner "test" -Repo "repo" -PR 123
  
  # Assert type
  $result | Should -BeOfType [System.Object[]]
  
  # Assert NOT double-nested
  $result[0] | Should -Not -BeOfType [System.Object[]]
  
  # Assert properties exist
  $result[0].number | Should -Be 123
  $result[0].title | Should -Not -BeNullOrEmpty
}
```

## Anti-Patterns

❌ **Idealized Mocks**: "I'll use PascalCase because it's cleaner"
✅ **Real Schema Mocks**: "Use exact casing from API response"

❌ **No Type Checks**: "Test property values only"
✅ **Type Assertions**: "Test type AND values"

❌ **Manual Schema**: "Copy from documentation"
✅ **Captured Schema**: "Execute API, save raw response"

## Related Skills

- **Skill-Testing-003**: Test fixtures from real API responses
- **Skill-Testing-008**: Entry point integration tests
- **Skill-PowerShell-004**: Avoid double-nested arrays

## Detection Strategy

**Warning Signs**:
- Unit tests pass, runtime fails
- Error: "property not found" or "cannot index into null"
- Type inspection shows unexpected structure
- Mocks use different casing than API

**Diagnostic Command**:
```powershell
# Inspect actual type returned
$result = YourFunction
$result | ForEach-Object { $_.GetType().FullName }

# Expected: System.Management.Automation.PSCustomObject
# Problem: System.Object[] (double-nested array)
```

## Reference Implementations

- **PR #402 Retrospective**: Double-nested array debugging session
- **Memory**: `testing-mock-fidelity.md`
- **Memory**: `powershell-array-handling.md`

## Validation

**Metric**: Zero test-pass-but-runtime-fail incidents = contract validated

**Evidence**: PR #402 double-nested array bug caught during live execution

**Impact**: High (prevents production bugs)

## Tags

- testing
- contract-testing
- api-mocks
- schema-validation
- type-safety
