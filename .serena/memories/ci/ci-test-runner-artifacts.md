# CI Test Runner and Artifacts

## Skill-CI-TestRunner-001: Reusable Test Runner Pattern (88%)

**Statement**: Extract test runner to build/scripts/ with CI and local modes for consistent execution.

```powershell
# build/scripts/Invoke-PesterTests.ps1
[CmdletBinding()]
param(
    [string]$TestPath = "./scripts/tests",
    [string]$OutputPath = "./artifacts/pester-results.xml",
    [string]$OutputFormat = "NUnitXml",
    [switch]$CI,        # Exit with error code on failure
    [switch]$PassThru   # Return result object
)

$config = New-PesterConfiguration
$config.Run.Path = $TestPath
$config.Run.Exit = $CI.IsPresent  # Only exit on failure in CI
$config.TestResult.Enabled = $true
$config.TestResult.OutputPath = $OutputPath

$result = Invoke-Pester -Configuration $config
if ($PassThru) { return $result }
```

**Usage**:

```powershell
# Local development
.\build\scripts\Invoke-PesterTests.ps1 -Verbosity Detailed

# CI pipeline
.\build\scripts\Invoke-PesterTests.ps1 -CI
```

## Skill-CI-Artifacts-001: Artifact Path Convention (85%)

**Statement**: Use artifacts/ directory for all test outputs; configure in single location.

```text
project/
  artifacts/           # All build outputs
    pester-results.xml
    coverage/
    logs/
  build/
    scripts/           # Build automation
```

```yaml
- uses: actions/upload-artifact@v4
  with:
    name: test-results
    path: ./artifacts/
    retention-days: 30
```
