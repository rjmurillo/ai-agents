# Skill-Testing-008: Entry Point Test Isolation

**Statement**: Code in entry points requires integration tests when unit tests blocked by dot-sourcing

**Atomicity**: 88%

**Context**: PowerShell scripts with entry point guard pattern `if ($MyInvocation.InvocationName -eq '.')`

**Evidence**: PR #402 - `TotalPRs` property untestable via unit tests, integration test required

## When to Apply

**Trigger Conditions**:
- Adding code to script entry points (after guard pattern)
- Entry point guard blocks unit test execution
- Code modifies script-level state (hashtables, arrays)
- Output generation logic (summaries, reports)

**Applies To**:
- PowerShell scripts with entry point isolation
- Code after `if ($MyInvocation.InvocationName -eq '.')` guard
- GitHub Actions step summary output
- Script initialization logic

## Entry Point Guard Pattern

```powershell
# ===== Functions (unit-testable via dot-sourcing) =====
function Get-PRComments { ... }
function Process-PR { ... }

# ===== Entry Point (NOT executed during dot-sourcing) =====
if ($MyInvocation.InvocationName -ne '.') {
    # This code ONLY runs when script executed directly
    # NOT when dot-sourced for unit tests
    
    $results = @{
        TotalPRs = 0        # <-- Cannot unit test this
        Processed = 0
    }
    
    # Process PRs
    $prs = Get-OpenPRs
    $results.TotalPRs = $prs.Count  # <-- Cannot unit test this
    
    # Write summary (entry point only)
    if ($env:GITHUB_STEP_SUMMARY) {
        @"
Total PRs: $($results.TotalPRs)
Processed: $($results.Processed)
"@ | Out-File $env:GITHUB_STEP_SUMMARY -Append
    }
}
```

## Why Unit Tests Fail

**Unit Test Attempt**:
```powershell
Describe "Script Execution" {
  BeforeAll {
    . ./scripts/Invoke-PRMaintenance.ps1  # Dot-source to load functions
  }
  
  It "sets TotalPRs property" {
    # This test CANNOT run because entry point guard prevents execution
    $results.TotalPRs | Should -Be 15  # FAILS: $results doesn't exist
  }
}
```

**Why It Fails**: Dot-sourcing (`. ./script.ps1`) triggers guard, entry point code skipped

## Integration Test Solution

```powershell
Describe "Integration: Script Execution" {
  It "processes PRs and writes summary" {
    # Execute script directly (NOT dot-sourced)
    $output = pwsh -File ./scripts/Invoke-PRMaintenance.ps1 -MaxPRs 5
    
    # Validate output
    $output | Should -Match "Total PRs: \d+"
    $output | Should -Match "Processed: \d+"
    
    # Validate side effects
    $env:GITHUB_STEP_SUMMARY | Should -Exist
    Get-Content $env:GITHUB_STEP_SUMMARY | Should -Match "Total PRs:"
  }
}
```

## Example (PR #402)

**Code Added**:
```powershell
# Line 818: Added to results hashtable
$results = @{
  TotalPRs = 0
  ...
}

# Line 832: Set during PR processing
$results.TotalPRs = $prs.Count

# Lines 972-1010: Write summary (entry point only)
if ($env:GITHUB_STEP_SUMMARY) {
  @"
Total PRs: $($results.TotalPRs)
Processed: $($results.Processed)
"@ | Out-File $env:GITHUB_STEP_SUMMARY -Append
}
```

**Test Gap**: Unit tests cannot access `$results.TotalPRs` (entry point variable)

**Risk Acceptance**:
- Code is isolated (no core logic)
- Existing 127 tests still pass (no regression)
- 42-line change, additive only
- Integration test validates end-to-end

## Test Strategy Decision Tree

```text
Is code in entry point? 
  ├─ NO → Unit test via dot-sourcing
  └─ YES → Is it core business logic?
      ├─ YES → Extract to function, unit test function
      └─ NO → Integration test via direct execution
```

## Anti-Patterns

❌ **Skip Testing**: "Entry point code can't be tested, skip it"
✅ **Integration Test**: "Use integration test for entry point isolation"

❌ **Extract Everything**: "Move all entry point code to functions"
✅ **Extract Logic Only**: "Keep initialization/output in entry point, extract business logic"

❌ **Ignore Guard**: "Disable guard to make unit tests work"
✅ **Respect Isolation**: "Guard prevents pollution, use integration tests"

## Related Skills

- **Skill-Testing-002**: Test-driven development
- **Skill-Testing-003**: Real API fixtures
- **Skill-PowerShell-002**: Always return arrays, never $null

## Risk Mitigation

**When to Accept Test Gap**:
- Code is < 50 lines
- Code is additive only (no deletions)
- Code has no branching logic
- Code is isolated (no shared state mutations)
- Existing tests still pass

**When to Require Tests**:
- Code has complex logic (if/else, loops)
- Code modifies shared state
- Code performs calculations
- Code has error handling

## Validation

**Metric**: Integration test passes = entry point code validated

**Evidence**: PR #402 - live execution confirmed summary output correct

**Impact**: Medium (prevents untested initialization bugs)

## Tags

- testing
- powershell
- entry-points
- integration-tests
- isolation

## Related

- [testing-002-test-first-development](testing-002-test-first-development.md)
- [testing-003-script-execution-isolation](testing-003-script-execution-isolation.md)
- [testing-004-coverage-pragmatism](testing-004-coverage-pragmatism.md)
- [testing-007-contract-testing](testing-007-contract-testing.md)
- [testing-coverage-philosophy-integration](testing-coverage-philosophy-integration.md)
