<#
.SYNOPSIS
    Runs Pester tests for the ai-agents PowerShell scripts.

.DESCRIPTION
    Executes Pester unit tests located in scripts/tests/ directory.
    Supports both CI/CD and local development scenarios.

    This script is called by:
    - .github/workflows/pester-tests.yml (CI/CD)
    - Local developers running tests manually
    - AI agents validating changes

.PARAMETER TestPath
    Path to the test directory or specific test file.
    Defaults to ./scripts/tests

.PARAMETER OutputPath
    Path for test result output file.
    Defaults to ./test-results/pester-results.xml

.PARAMETER OutputFormat
    Format for test results. Valid values: NUnitXml, JUnitXml
    Defaults to NUnitXml

.PARAMETER Verbosity
    Output verbosity level. Valid values: None, Normal, Detailed, Diagnostic
    Defaults to Detailed

.PARAMETER CI
    Run in CI mode (exit with error code on test failure).
    Defaults to false for local runs.

.PARAMETER PassThru
    Return the Pester result object for programmatic access.

.EXAMPLE
    .\Invoke-PesterTests.ps1
    # Run all tests with default settings (local development)

.EXAMPLE
    .\Invoke-PesterTests.ps1 -CI
    # Run tests in CI mode (exits with error on failure)

.EXAMPLE
    .\Invoke-PesterTests.ps1 -TestPath "./scripts/tests/Install-Common.Tests.ps1"
    # Run specific test file

.EXAMPLE
    .\Invoke-PesterTests.ps1 -Verbosity Diagnostic -PassThru
    # Run with maximum verbosity and return result object
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$TestPath = "./scripts/tests",

    [Parameter()]
    [string]$OutputPath = "./test-results/pester-results.xml",

    [Parameter()]
    [ValidateSet("NUnitXml", "JUnitXml")]
    [string]$OutputFormat = "NUnitXml",

    [Parameter()]
    [ValidateSet("None", "Normal", "Detailed", "Diagnostic")]
    [string]$Verbosity = "Detailed",

    [Parameter()]
    [switch]$CI,

    [Parameter()]
    [switch]$PassThru
)

$ErrorActionPreference = "Stop"

# Resolve paths relative to repository root
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$TestPath = Join-Path $RepoRoot $TestPath.TrimStart("./").TrimStart(".\")
$OutputPath = Join-Path $RepoRoot $OutputPath.TrimStart("./").TrimStart(".\")

Write-Host ""
Write-Host "=== Pester Test Runner ===" -ForegroundColor Cyan
Write-Host "Repository Root: $RepoRoot"
Write-Host "Test Path: $TestPath"
Write-Host "Output Path: $OutputPath"
Write-Host "Output Format: $OutputFormat"
Write-Host "Verbosity: $Verbosity"
Write-Host "CI Mode: $CI"
Write-Host ""

# Verify Pester is installed
$pester = Get-Module -ListAvailable -Name Pester | Where-Object { $_.Version -ge [version]"5.0.0" } | Select-Object -First 1
if (-not $pester) {
    Write-Host "Pester 5.0+ not found. Installing..." -ForegroundColor Yellow
    Set-PSRepository -Name 'PSGallery' -InstallationPolicy Trusted
    Install-Module -Name Pester -MinimumVersion 5.0.0 -Force -Scope CurrentUser
    Import-Module Pester -MinimumVersion 5.0.0
    $pester = Get-Module Pester
}
Write-Host "Using Pester version: $($pester.Version)" -ForegroundColor Green

# Verify test path exists
if (-not (Test-Path $TestPath)) {
    Write-Error "Test path not found: $TestPath"
    exit 1
}

# Create output directory if needed
$OutputDir = Split-Path -Parent $OutputPath
if (-not (Test-Path $OutputDir)) {
    Write-Host "Creating output directory: $OutputDir" -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

# Configure Pester
$config = New-PesterConfiguration
$config.Run.Path = $TestPath
$config.Run.Exit = $CI.IsPresent
$config.Run.PassThru = $true
$config.TestResult.Enabled = $true
$config.TestResult.OutputFormat = $OutputFormat
$config.TestResult.OutputPath = $OutputPath
$config.Output.Verbosity = $Verbosity

# Run tests
Write-Host "Running tests..." -ForegroundColor Cyan
Write-Host ""

$result = Invoke-Pester -Configuration $config

# Display summary
Write-Host ""
Write-Host "=== Test Summary ===" -ForegroundColor Cyan
Write-Host "Tests Run: $($result.TotalCount)"
Write-Host "Passed: $($result.PassedCount)" -ForegroundColor Green
Write-Host "Failed: $($result.FailedCount)" -ForegroundColor $(if ($result.FailedCount -gt 0) { "Red" } else { "Green" })
Write-Host "Skipped: $($result.SkippedCount)" -ForegroundColor Yellow
Write-Host "Duration: $($result.Duration.TotalSeconds.ToString('F2'))s"
Write-Host ""

if ($result.FailedCount -gt 0) {
    Write-Host "FAILED: $($result.FailedCount) test(s) failed" -ForegroundColor Red

    if (-not $CI) {
        Write-Host ""
        Write-Host "Failed tests:" -ForegroundColor Red
        $result.Failed | ForEach-Object {
            Write-Host "  - $($_.ExpandedPath)" -ForegroundColor Red
        }
    }
}
else {
    Write-Host "SUCCESS: All tests passed" -ForegroundColor Green
}

Write-Host ""
Write-Host "Test results saved to: $OutputPath"

# Return result object if requested
if ($PassThru) {
    return $result
}

# Exit with appropriate code for local runs
if (-not $CI -and $result.FailedCount -gt 0) {
    exit 1
}
