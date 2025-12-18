# Retrospective Learnings: CI Test Failures (2025-12-17)

**Session**: Fixed 4 pre-existing Pester test failures in CI run 20324607494 (PR #55)
**Outcome**: Success - All 108 tests passing
**Commit**: 9572abf

## Executive Summary

Fixed 4 test failures caused by environment asymmetry between local and CI:

1. Path normalization: Windows 8.3 short names broke string operations
2. Exit code ordering: gh CLI check before parameter validation (3 tests)
3. XML corruption: ANSI escape codes invalid in XML output

**Root Pattern**: Environment asymmetry - tests passing locally but failing in CI due to path normalization, external tool availability, and structured output requirements.

## Critical Skills Extracted

### Skill-PowerShell-Path-Normalization-001

**Statement**: Use Resolve-Path -Relative with Push-Location to calculate relative paths on Windows

**Evidence**: Windows 8.3 short name normalization (RUNNER~1 vs runneradmin) caused `Substring($rootPath.Length)` to fail with index out of range

**Pattern**:

```powershell
Push-Location $rootPath
try {
    $relativePath = Resolve-Path -Path $filePath -Relative
    $relativePath = $relativePath -replace '^\.[\\/]', ''
} finally {
    Pop-Location
}
```

**Atomicity**: 94%
**Impact**: 9/10

---

### Skill-Testing-Exit-Code-Order-001

**Statement**: Validate parameters before checking external tool availability for predictable exit codes

**Evidence**: Post-PRCommentReply.ps1 returned exit 4 (gh auth failure) instead of expected 1/2 (parameter errors) because gh CLI check ran before parameter validation - broke 3 tests

**Pattern**:

```powershell
# 1. Validate parameters first (pure logic)
if (-not $Body -and -not $BodyFile) { exit 2 }
if ($BodyFile -and -not (Test-Path $BodyFile)) { exit 1 }

# 2. Then check external tools (environment dependencies)
if (-not (Test-GhAuthenticated)) { exit 4 }
```

**Reasoning**: Parameter validation is pure logic and should be independent of environment state (gh CLI availability). Tests can't control environment but expect specific exit codes for parameter errors.

**Atomicity**: 92%
**Impact**: 10/10

---

### Skill-CI-ANSI-Disable-001

**Statement**: Disable ANSI codes in CI via NO_COLOR env var and PSStyle.OutputRendering PlainText

**Evidence**: ANSI escape codes (0x1B) in Pester output corrupted XML report, causing test-reporter GitHub Action to fail

**Pattern**:

```powershell
if ($CI) {
    $env:NO_COLOR = '1'
    $env:TERM = 'dumb'
    if ($PSVersionTable.PSVersion.Major -ge 7) {
        $PSStyle.OutputRendering = 'PlainText'
    }
}

# In scripts that output colors
$NoColor = $env:NO_COLOR -or $env:TERM -eq 'dumb' -or $env:CI
if ($NoColor) {
    $ColorRed = ""
    $ColorGreen = ""
} else {
    $ColorRed = "`e[31m"
    $ColorGreen = "`e[32m"
}
```

**Why it matters**: XML parsers reject ANSI escape codes as invalid characters. Structured output requires plain text.

**Atomicity**: 90%
**Impact**: 9/10

---

### Skill-CI-Environment-Testing-001

**Statement**: Test scripts locally with temp paths and no auth to catch CI environment failures

**Evidence**: All 4 failures passed locally but failed in CI due to:

- Windows 8.3 paths in temp directories
- gh CLI unavailability/unauthenticated
- XML output format (vs console output locally)

**Local CI Simulation**:

```powershell
# Simulate CI temp paths
$env:TEMP = "C:\Users\RUNNER~1\AppData\Local\Temp"

# Remove auth
Remove-Item Env:\GH_TOKEN -ErrorAction SilentlyContinue

# Run tests in CI mode
Invoke-PesterTests -CI
```

**Atomicity**: 88%
**Impact**: 8/10

---

## Anti-Patterns Identified

### Anti-Pattern-PowerShell-Path-String-001

**Statement**: Never use string Substring operations on file paths; use Resolve-Path cmdlets instead

**Why harmful**: Windows path normalization (8.3 short names, case insensitivity) means the same path can have multiple string representations. String operations like `Substring($rootPath.Length)` fail when representations differ.

**Example**:

```powershell
# WRONG: Brittle string manipulation
$relativePath = $fullPath.Substring($rootPath.Length).TrimStart('\', '/')

# RIGHT: Robust path cmdlet
$relativePath = Resolve-Path -Path $fullPath -Relative
```

**Tag**: harmful
**Atomicity**: 96%

---

### Anti-Pattern-External-Check-First-001

**Statement**: External tool checks before parameter validation return unpredictable exit codes

**Why harmful**: Tests expect specific exit codes for parameter validation errors (1, 2), but if external tool check (e.g., gh CLI auth) runs first, it returns its own exit code (4), making tests fail.

**Example**:

```powershell
# WRONG: External check first
if (-not (Test-GhAuthenticated)) { exit 4 }
if (-not $Body) { exit 2 }  # Never reached if gh check fails

# RIGHT: Parameters first
if (-not $Body) { exit 2 }
if (-not (Test-GhAuthenticated)) { exit 4 }
```

**Tag**: harmful
**Atomicity**: 85%

---

## Five Whys: Environment Asymmetry Pattern

**Q1**: Why did tests pass locally but fail in CI?
**A1**: Different environment states (paths, auth, output format)

**Q2**: Why did environment differences matter?
**A2**: Code made assumptions about environment consistency

**Q3**: Why did code assume environment consistency?
**A3**: Only tested in local environment, not CI-like conditions

**Q4**: Why weren't CI-like conditions tested locally?
**A4**: No local CI simulation mode or pattern

**Q5**: Why does this matter?
**A5**: Fast feedback loop requires catching CI failures before push

**Root Cause**: Lack of CI environment simulation in local development

**Prevention**:

1. Add `-CI` flag to `Invoke-PesterTests.ps1` for local CI simulation
2. Test with temp paths and no external auth before pushing
3. Use PowerShell cmdlets that handle environment variations (path normalization, etc.)

---

## Key Insights

### Pattern 1: Environment Asymmetry (3/4 failures)

Tests passing locally but failing in CI due to:

- Path representation differences (8.3 short names)
- External tool availability (gh CLI)
- Output format requirements (console vs XML)

**Impact**: High - Entire class of failures
**Prevention**: Local CI simulation, environment-agnostic code patterns

### Pattern 2: Structured Output Contamination

Human-friendly output (ANSI colors) breaks machine-readable formats (XML). Need plain text mode for structured output.

**Impact**: Medium - Breaks CI reporting infrastructure
**Prevention**: Detect output mode and disable formatting for structured formats

### Pattern 3: Validation Layer Ordering

Pure logic validation (parameters) must run before environmental checks (external tools) for predictable behavior.

**Impact**: High - Test reliability
**Prevention**: Always validate parameters before checking environment state

---

## Related Memories

- **powershell-testing-patterns**: Parameter combination testing, ShouldProcess+PassThru
- **pester-test-isolation-pattern**: BeforeEach cleanup for test isolation
- **skills-pester-testing**: Pester 5.x BeforeAll patterns, -ForEach migrations
- **skills-ci-infrastructure**: CI/CD workflow patterns (UPDATE with ANSI skills)

---

## Recommendations

### Immediate Actions

1. ✅ Document path normalization pattern in skills
2. ✅ Document exit code ordering in skills
3. ✅ Document ANSI disabling pattern in skills
4. Add CI simulation mode to local test runner
5. Add pre-commit hook to run tests with `-CI` flag

### Long-term Improvements

1. **CI Environment Simulator**: Docker container matching GitHub Actions environment
2. **Path Operation Linting**: Detect string operations on paths, suggest cmdlets
3. **Test Environment Matrix**: Explicitly test with/without auth, with temp paths
4. **Exit Code Documentation**: Document expected exit codes in function headers

---

## Files Modified

- `build/scripts/Validate-PathNormalization.ps1`: Path normalization + NO_COLOR respect
- `.claude/skills/github-pr-reply/scripts/Post-PRCommentReply.ps1`: Validation reordering
- `build/scripts/Invoke-PesterTests.ps1`: ANSI disabling in CI mode

**Test Results**: 104/108 → 108/108 passing (0 failures)
