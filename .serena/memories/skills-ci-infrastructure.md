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

## Related Files

- Test Runner: `build/scripts/Invoke-PesterTests.ps1`
- Pester Workflow: `.github/workflows/pester-tests.yml`
- Copilot Setup: `.github/workflows/copilot-setup-steps.yml`
