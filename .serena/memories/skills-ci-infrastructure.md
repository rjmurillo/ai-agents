# CI Infrastructure Skills

**Extracted**: 2025-12-15
**Source**: ai-agents install scripts session - CI/CD setup

## Skill-CI-TestRunner-001: Reusable Test Runner Pattern

**Statement**: Extract test runner to build/scripts/ with CI and local modes for consistent execution

**Context**: When creating CI/CD pipelines that developers can also run locally

**Evidence**: Invoke-PesterTests.ps1 with -CI switch used by workflow and developers

**Atomicity**: 88%

**Pattern**:

```powershell
# build/scripts/Invoke-PesterTests.ps1
[CmdletBinding()]
param(
    [string]$TestPath = "./scripts/tests",
    [string]$OutputPath = "./artifacts/pester-results.xml",
    [ValidateSet("NUnitXml", "JUnitXml")]
    [string]$OutputFormat = "NUnitXml",
    [ValidateSet("None", "Normal", "Detailed", "Diagnostic")]
    [string]$Verbosity = "Detailed",
    [switch]$CI,        # Exit with error code on failure
    [switch]$PassThru   # Return result object
)

# Configure Pester
$config = New-PesterConfiguration
$config.Run.Path = $TestPath
$config.Run.Exit = $CI.IsPresent  # Only exit on failure in CI mode
$config.Run.PassThru = $true
$config.TestResult.Enabled = $true
$config.TestResult.OutputFormat = $OutputFormat
$config.TestResult.OutputPath = $OutputPath

$result = Invoke-Pester -Configuration $config

# Local mode: return result for inspection
if ($PassThru) { return $result }
```

**Usage**:

```powershell
# Local development
.\build\scripts\Invoke-PesterTests.ps1 -Verbosity Detailed

# CI pipeline
.\build\scripts\Invoke-PesterTests.ps1 -CI
```

**Workflow Integration**:

```yaml
# .github/workflows/pester-tests.yml
- name: Run Pester Tests
  shell: pwsh
  run: ./build/scripts/Invoke-PesterTests.ps1 -CI
```

---

## Skill-CI-Artifacts-001: Artifact Path Convention

**Statement**: Use artifacts/ directory for all test outputs; configure in single location

**Context**: When standardizing build artifact locations

**Evidence**: Consolidated test output to artifacts/pester-results.xml

**Atomicity**: 85%

**Pattern**:

```text
project/
  artifacts/           # All build outputs
    pester-results.xml
    coverage/
    logs/
  build/
    scripts/           # Build automation
      Invoke-PesterTests.ps1
  .github/
    workflows/
      pester-tests.yml
```

**Benefits**:

- Single location for CI to upload artifacts
- Easy to add to .gitignore
- Consistent across different test frameworks
- Matches common CI/CD conventions

**Configuration**:

```yaml
# .github/workflows/pester-tests.yml
- uses: actions/upload-artifact@v4
  with:
    name: test-results
    path: ./artifacts/
    retention-days: 30
```

---

## Skill-CI-Runner-001: Prefer Linux Runners

**Statement**: Prefer ubuntu-latest over windows-latest for GitHub Actions runners - MUCH faster

**Context**: GitHub Actions workflow configuration

**Evidence**: User feedback on PR #47: "prefer 'linux-latest' runners. MUCH faster"

**Atomicity**: 95%

**Tag**: helpful

**Impact**: 8/10

**Exceptions**:

- PowerShell Desktop required (not pwsh/PowerShell Core)
- Windows-specific features or APIs needed
- Testing Windows-only behavior

**Pattern**:

```yaml
# Default: Use Linux
jobs:
  build:
    runs-on: ubuntu-latest
    
# Exception: Windows-specific testing
  windows-test:
    runs-on: windows-latest
    if: needs.check.outputs.windows-required == 'true'
```

---

---

## Skill-CI-ANSI-Disable-001: Disable ANSI in CI Mode

**Statement**: Disable ANSI codes in CI via NO_COLOR env var and PSStyle.OutputRendering PlainText

**Context**: When PowerShell scripts with console color output are used in CI pipelines that generate XML or structured reports

**Evidence**: CI run 20324607494: ANSI escape codes (0x1B) corrupted Pester XML report, causing test-reporter GitHub Action to fail

**Atomicity**: 90%

**Tag**: helpful

**Impact**: 9/10

**Pattern**:

```powershell
# In test runner (Invoke-PesterTests.ps1)
if ($CI) {
    $env:NO_COLOR = '1'
    $env:TERM = 'dumb'
    if ($PSVersionTable.PSVersion.Major -ge 7) {
        $PSStyle.OutputRendering = 'PlainText'
    }
}
```

```powershell
# In scripts that output colors (Validate-PathNormalization.ps1)
$NoColor = $env:NO_COLOR -or $env:TERM -eq 'dumb' -or $env:CI

if ($NoColor) {
    $ColorRed = ""
    $ColorGreen = ""
    $ColorReset = ""
} else {
    $ColorRed = "`e[31m"
    $ColorGreen = "`e[32m"
    $ColorReset = "`e[0m"
}

function Write-ColorOutput {
    param([string]$Message, [string]$Color = $ColorReset)
    
    if ($NoColor) {
        Write-Host $Message
    } else {
        Write-Host "$Color$Message$ColorReset"
    }
}
```

**Why it matters**:

- ANSI escape codes (0x1B) are invalid XML characters
- XML parsers reject files with control characters
- CI reporting infrastructure (test-reporter) requires valid XML
- NO_COLOR is a standard environment variable for disabling colors

**Standards Respected**:

- [NO_COLOR](https://no-color.org/): Standard environment variable
- TERM=dumb: Traditional Unix signal for non-interactive mode
- PSStyle.OutputRendering: PowerShell 7+ native plain text mode

---

## Skill-CI-Environment-Testing-001: Local CI Simulation

**Statement**: Test scripts locally with temp paths and no auth to catch CI environment failures

**Context**: Before pushing PowerShell scripts that will run in GitHub Actions or other CI environments

**Evidence**: CI run 20324607494: All 4 test failures passed locally but failed in CI due to Windows 8.3 paths, gh CLI unavailability, and XML output format

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10

**Pattern**:

```powershell
# Local CI simulation
function Test-InCIMode {
    # Simulate CI temp paths (Windows 8.3 short names)
    $originalTemp = $env:TEMP
    $env:TEMP = "C:\Users\RUNNER~1\AppData\Local\Temp"
    
    # Remove auth tokens
    $originalGH = $env:GH_TOKEN
    Remove-Item Env:\GH_TOKEN -ErrorAction SilentlyContinue
    
    try {
        # Run tests in CI mode
        Invoke-PesterTests -CI
    }
    finally {
        # Restore environment
        $env:TEMP = $originalTemp
        if ($originalGH) { $env:GH_TOKEN = $originalGH }
    }
}
```

**Environment Differences to Simulate**:

1. **Path normalization**: Windows 8.3 short names (RUNNER~1 vs full names)
2. **External auth**: gh CLI, git credentials unavailable
3. **Output format**: XML reports instead of console output
4. **Environment variables**: CI=true, NO_COLOR=1, TERM=dumb

**Pre-push Checklist**:

- [ ] Run tests with `-CI` flag
- [ ] Test with temp directory paths
- [ ] Test without gh CLI authentication
- [ ] Verify XML output is valid (no ANSI codes)

---

## Related Files

- Test Runner: `build/scripts/Invoke-PesterTests.ps1`
- Pester Workflow: `.github/workflows/pester-tests.yml`
- Copilot Setup: `.github/workflows/copilot-setup-steps.yml`
- Retrospective: `.agents/retrospective/2025-12-17-ci-test-failures-xml-corruption.md`
- Source: `.agents/retrospective/pr-feedback-remediation.md`
