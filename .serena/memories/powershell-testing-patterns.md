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

---

## Skill-PowerShell-Path-Normalization-001: Relative Path Calculation

**Statement**: Use Resolve-Path -Relative with Push-Location to calculate relative paths on Windows

**Context**: When calculating relative paths from absolute paths in PowerShell scripts that may run in different Windows environments

**Evidence**: CI run 20324607494: Windows 8.3 short name normalization (RUNNER~1 vs runneradmin) caused Substring($rootPath.Length) to fail with index out of range; Resolve-Path -Relative handles normalization correctly

**Atomicity**: 94%

**Tag**: helpful

**Impact**: 9/10

**Pattern**:

```powershell
# WRONG: Brittle string manipulation
$relativePath = $fileGroup.Name.Substring($rootPath.Length).TrimStart('\', '/')

# RIGHT: Robust path cmdlet with normalization
Push-Location $rootPath
try {
    $relativePath = Resolve-Path -Path $fileGroup.Name -Relative
    # Remove leading .\ or ./
    $relativePath = $relativePath -replace '^\.[\\/]', ''
}
finally {
    Pop-Location
}
```

**Why it matters**:

- Windows path normalization is inconsistent (8.3 short names vs full names)
- CI environments use temp paths that may trigger 8.3 naming (RUNNER~1)
- String operations like `Substring($rootPath.Length)` assume consistent representations
- `Resolve-Path -Relative` handles all normalization cases correctly
- `Push-Location` sets working directory for relative path calculation

**Anti-Pattern**: Never use string Substring operations on file paths

**Validated**: 1 (CI run 20324607494)

---

## Skill-Testing-Exit-Code-Order-001: Parameter Validation First

**Statement**: Validate parameters before checking external tool availability for predictable exit codes

**Context**: When writing PowerShell scripts with parameter validation and external tool dependencies (gh CLI, git, etc.) that will be tested

**Evidence**: CI run 20324607494: Post-PRCommentReply.ps1 returned exit 4 (gh auth) instead of exit 1/2 (parameter validation) because gh CLI check ran first; reordering validation fixed 3 test failures

**Atomicity**: 92%

**Tag**: helpful

**Impact**: 10/10

**Pattern**:

```powershell
#region Validation

# 1. FIRST: Validate parameters (pure logic, independent of environment)
if (-not $Body -and -not $BodyFile) {
    Write-ErrorAndExit "Either -Body or -BodyFile must be provided." 2
}

if ($BodyFile -and -not (Test-Path $BodyFile)) {
    Write-ErrorAndExit "BodyFile not found: $BodyFile" 1
}

if ($CommentType -eq "review" -and -not $CommentId) {
    Write-ErrorAndExit "CommentId required for review comments." 1
}

# 2. THEN: Check external tool availability (environment-dependent)
if (-not (Test-GhAuthenticated)) {
    Write-ErrorAndExit "gh CLI not authenticated. Run 'gh auth login'." 4
}

#endregion
```

**Reasoning**:

- Parameter validation is pure logic and should be independent of environment state
- External tool availability depends on environment (gh CLI installed, authenticated)
- Tests can't control environment but expect specific exit codes for parameter errors
- Exit code 1: Invalid file path
- Exit code 2: Missing required parameter
- Exit code 4: External tool unavailable

**Test Pattern**:

```powershell
It "Returns exit code 1 when BodyFile does not exist" {
    $result = Post-PRCommentReply -PullRequest 123 -BodyFile "nonexistent.txt"
    $LASTEXITCODE | Should -Be 1
}

It "Returns exit code 2 when both Body and BodyFile are missing" {
    $result = Post-PRCommentReply -PullRequest 123
    $LASTEXITCODE | Should -Be 2
}
```

**Anti-Pattern**: External tool checks before parameter validation return unpredictable exit codes

**Validated**: 1 (CI run 20324607494, 3 tests fixed)

---

## Skill-PowerShell-Wildcard-Escaping-001: Bracket Escaping for -like Operator

**Statement**: Use bracket notation `[?]` and `[*]` to match literal wildcard characters in PowerShell -like comparisons

**Context**: When detecting wildcard characters in file paths or patterns for conditional logic in PowerShell scripts

**Evidence**: PR #55 commit 106d211: Condition `$fullPath -like "*?*"` always evaluated to true (matches ANY 2+ char string); fix changed to `$fullPath -like "*[?]*"` to match literal `?` character

**Atomicity**: 95%

**Tag**: helpful

**Impact**: 10/10

**Pattern**:

```powershell
# WRONG: ? is treated as wildcard (matches any single char)
if ($path -like "*?*") {  # Matches "ab", "test.txt", etc.
    # This branch taken for ANY path with 2+ characters!
}

# WRONG: * is treated as wildcard (matches zero or more chars)
if ($path -like "**") {  # Matches any string including empty
    # This branch taken for ALL paths!
}

# RIGHT: Bracket notation matches literal characters
if ($path -like "*[?]*") {  # Only matches paths containing literal ?
    # Correctly detects wildcard character
}

if ($path -like "*[*]*") {  # Only matches paths containing literal *
    # Correctly detects wildcard character
}
```

**Why it matters**:

- PowerShell `-like` operator uses wildcards: `?` (any single char), `*` (zero or more chars)
- To match literal wildcard characters, use bracket notation: `[?]`, `[*]`
- Without brackets, conditions like `"*?*"` match almost any string
- Can create dead code branches when condition always evaluates to true

**Anti-Pattern**: Using unescaped wildcard chars in -like when checking for literal characters

**Test Pattern**:

```powershell
It "Should detect literal ? in filename" {
    $path = "test?.ps1"
    $path -like "*[?]*" | Should -Be $true
}

It "Should not match paths without literal ?" {
    $path = "test.ps1"
    $path -like "*[?]*" | Should -Be $false
}
```

**Validated**: 1 (PR #55 commit 106d211)

---

## Skill-Testing-Platform-001: Document Platform Requirements (90%)

**Statement**: When reverting multi-platform tests to single-platform, add YAML comments in workflow file documenting specific platform assumptions

**Context**: When Pester tests fail on Linux/ARM but pass on Windows

**Trigger**: Reverting workflow runners from cross-platform to Windows-only

**Location Rationale**: Bundled in powershell-testing-patterns.md per ADR-019 Format B (8+ related testing skills share workflow context)

**Evidence**: PR #224: Pester tests failed on ARM Linux due to Windows-specific assumptions about hidden files, temp paths, and file system behavior. Tests reverted to Windows with documented justification.

**Atomicity**: 90%

**Tag**: helpful (prevents future migration attempts without fixing root cause)

**Impact**: 8/10

**Created**: 2025-12-23

**Pattern**:

```yaml
# Document why Windows is required
test:
  name: Run Pester Tests
  # Keep on Windows - many tests have Windows-specific assumptions
  # (file paths, hidden files, etc.) that don't work on Linux ARM
  runs-on: windows-latest
```

**Why It Matters**:

Without documentation, future engineers may attempt ARM migration again and face the same failures. Documenting specific assumptions (hidden file behavior, temp path differences, path separator assumptions) creates a clear remediation path.

**Follow-up Work**:

1. Create issue tracking platform assumptions
2. Gradually fix tests to be cross-platform
3. Re-attempt migration after fixes

**Validation**: 1 (PR #224)

---

## Skill-Testing-Path-001: Absolute Paths for Cross-Directory Imports (91%)

**Statement**: Use explicit absolute paths (via `$PSScriptRoot` with multiple `..` segments) for test imports that cross directory hierarchies

**Context**: When test files in `.github/tests/skills/` need to import modules from `.claude/skills/`

**Trigger**: Writing Pester tests that import shared modules from different directory trees

**Evidence**: PR #255: `New-Issue.Tests.ps1` had `Join-Path $PSScriptRoot ".." "modules"` which resolved to wrong location. Fixed with explicit path `Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "modules"`

**Atomicity**: 91%

**Tag**: helpful (prevents import failures)

**Impact**: 8/10

**Created**: 2025-12-23

**Problem**:

```powershell
# WRONG: Assumes module is nearby
$ModulePath = Join-Path $PSScriptRoot ".." "modules" "GitHubHelpers.psm1"
# Resolves to: .github/tests/skills/modules/GitHubHelpers.psm1 (doesn't exist!)
```

**Solution**:

```powershell
# CORRECT: Explicit path from test location to actual module location
# From: .github/tests/skills/github/
# To:   .claude/skills/github/modules/
$ModulePath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "modules" "GitHubHelpers.psm1"
```

**Why It Matters**:

Test files and source files may be in different directory trees for organization reasons. Tests must explicitly navigate from their location to the source location. Using short relative paths assumes nearby files that may not exist.

**Best Practice**:

```powershell
BeforeAll {
    # Comment explaining the path navigation
    # From: .github/tests/skills/github -> .claude/skills/github/...
    $ScriptPath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "scripts" "pr" "Close-PR.ps1"
    $ModulePath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "modules" "GitHubHelpers.psm1"
    
    Import-Module $ModulePath -Force
}
```

**Validation**: 1 (PR #255)

---

## Related Skills

- See above formal skills section for Skill-PowerShell-Testing-Combinations-001, Skill-PowerShell-Parameter-Patterns-001, Skill-PowerShell-Testing-Process-001, Skill-PowerShell-Path-Normalization-001, Skill-Testing-Exit-Code-Order-001, Skill-PowerShell-Wildcard-Escaping-001
