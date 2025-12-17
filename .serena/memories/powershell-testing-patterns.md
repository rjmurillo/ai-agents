# PowerShell Testing Patterns

## Parameter Combination Testing

### Formula

For cmdlets with n switch parameters:

- n individual tests (one parameter at a time)
- C(n,2) pair tests (all unique combinations)
- **Minimum total: n + C(n,2)**

### Common Parameter Counts

| Params | Individual | Pairs | Total |
|--------|------------|-------|-------|
| 2 | 2 | 1 | 3 |
| 3 | 3 | 3 | 6 |
| 4 | 4 | 6 | 10 |

### Test Structure Template

```powershell
Describe "Cmdlet-Name" {
    Context "Basic Functionality" {
        # Core operation tests
    }

    Context "Error Handling" {
        # Invalid input, missing files, etc.
    }

    Context "Parameter Combinations" {
        It "Works with WhatIf + PassThru" { }
        It "Works with Force + PassThru" { }
        It "Works with Force + WhatIf" { }
    }

    Context "Edge Cases" {
        It "Handles first-time setup" { }
    }
}
```

## ShouldProcess + PassThru Pattern

### Required Implementation

```powershell
if ($PSCmdlet.ShouldProcess($target, $action)) {
    # Perform operation
    if ($PassThru) { return $true }
} else {
    # WhatIf or Confirm declined
    if ($PassThru) { return $false }  # ← REQUIRED!
}
```

### Why Else-Branch is Required

- WhatIf makes ShouldProcess return `$false`
- Code inside if-block never executes
- Without else-branch, PassThru returns nothing
- Breaks the parameter contract (should return boolean)

### Test for This Pattern

```powershell
It "Returns false when WhatIf is used with PassThru" {
    $result = Cmdlet-Name -WhatIf -PassThru
    $result | Should -Be $false
}
```

## Test-First Process for Cmdlets

1. **Define signature** with parameter attributes
2. **Write combination tests** (expect failures)
3. **Implement** to pass tests
4. **Refactor** with test safety

### Benefits

- Surfaces edge cases during development
- Tests guide implementation
- Fewer issues found in code review

## Evidence

PR #52: Copilot identified two issues:

1. Missing return value for WhatIf+PassThru
2. Missing test for this combination

Test suite had 16 tests but missed this combination because tests were organized by feature (WhatIf section, PassThru section) not by combinations.

## Formal Skills

### Skill-PowerShell-Testing-Combinations-001

**Statement**: PowerShell cmdlets with 2+ switch parameters require combination tests: n parameters = n individual + C(n,2) pairs minimum

**Context**: When writing Pester tests for PowerShell cmdlets that accept multiple switch parameters (Force, WhatIf, PassThru, Confirm, etc.)

**Evidence**: PR #52 Issues 2 & 3: Test suite had 16 tests but missed WhatIf+PassThru combination, allowing return value bug to exist undetected

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 9/10

**Created**: 2025-12-17

**Validated**: 1 (PR #52)

**Formula**: 2 params = 2 individual + 1 pair = 3 tests; 3 params = 3 individual + 3 pairs = 6 tests

---

### Skill-PowerShell-Parameter-Patterns-001

**Statement**: ShouldProcess with PassThru: provide explicit return value in else branch when ShouldProcess returns false

**Context**: When implementing PowerShell cmdlets that combine [CmdletBinding(SupportsShouldProcess)] with a -PassThru switch parameter

**Evidence**: PR #52 Issue 2: When WhatIf used with PassThru, no return value because return statement was only in if-branch. Fix added `else { if ($PassThru) { return $false } }`

**Atomicity**: 85%

**Tag**: helpful

**Impact**: 10/10

**Created**: 2025-12-17

**Validated**: 1 (PR #52)

**Code Example**:

```powershell
if ($PSCmdlet.ShouldProcess(...)) {
    if ($PassThru) { return $true }
} else {
    if ($PassThru) { return $false }  # Required!
}
```

---

### Skill-PowerShell-Testing-Process-001

**Statement**: For PowerShell cmdlets: write parameter combination tests before implementation to surface edge cases early

**Context**: When starting implementation of a new PowerShell cmdlet, especially those with SupportsShouldProcess or multiple switch parameters

**Evidence**: PR #52 Issues 2 & 3: Tests written after implementation missed WhatIf+PassThru case. If tests were first, would have failed immediately.

**Atomicity**: 90%

**Tag**: helpful

**Impact**: 9/10

**Created**: 2025-12-17

**Validated**: 1 (PR #52)

**Process**:

1. Define cmdlet signature with parameters
2. Write parameter combination tests (expect failures)
3. Implement cmdlet to pass tests

## Related Skills

- See above formal skills section for Skill-PowerShell-Testing-Combinations-001, Skill-PowerShell-Parameter-Patterns-001, Skill-PowerShell-Testing-Process-001
