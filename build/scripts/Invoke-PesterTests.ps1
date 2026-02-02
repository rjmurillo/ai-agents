<#
.SYNOPSIS
    Runs Pester tests for the ai-agents PowerShell scripts.

.DESCRIPTION
    Executes Pester unit tests located in multiple test directories:
    - scripts/tests/ - Installation script tests
    - build/scripts/tests/ - Build script tests
    - build/tests/ - Code generation tests
    - .claude/skills/*/tests/ - Claude skill tests
    - .github/scripts/ - GitHub workflow script tests
    - .github/tests/** - GitHub skill tests (relocated from .claude/skills)
    
    Supports both CI/CD and local development scenarios.

    This script is called by:
    - .github/workflows/pester-tests.yml (CI/CD)
    - Local developers running tests manually
    - AI agents validating changes

.PARAMETER TestPath
    Array of paths to test directories or specific test files.
    Supports wildcards for pattern matching (e.g., "./.claude/skills/*/tests")
    Defaults to all standard test locations in the repository.

.PARAMETER OutputPath
    Path for test result output file.
    Defaults to ./artifacts/pester-results.xml

.PARAMETER OutputFormat
    Format for test results. Valid values: NUnitXml, JUnitXml
    Defaults to JUnitXml

.PARAMETER Verbosity
    Output verbosity level. Valid values: None, Normal, Detailed, Diagnostic
    Defaults to Detailed

.PARAMETER CI
    Run in CI mode (exit with error code on test failure).
    Defaults to false for local runs.

.PARAMETER PassThru
    Return the Pester result object for programmatic access.

.PARAMETER EnableCodeCoverage
    Enable code coverage analysis.
    Generates coverage report in artifacts/TestResults/coverage.xml

.PARAMETER CoverageOutputPath
    Path for code coverage output file.
    Defaults to ./artifacts/TestResults/coverage.xml
    Only used when EnableCodeCoverage is specified.

.PARAMETER CoverageFormat
    Format for code coverage report. Valid values: JaCoCo, CoverageGutters
    Defaults to JaCoCo (XML format compatible with most CI tools)
    Only used when EnableCodeCoverage is specified.

.PARAMETER CheckCoverageThreshold
    Check code coverage against baseline thresholds from .baseline/coverage-thresholds.json
    Fails the build if coverage drops below the threshold.
    Only used when EnableCodeCoverage is specified.

.EXAMPLE
    .\Invoke-PesterTests.ps1
    # Run all tests from all standard locations

.EXAMPLE
    .\Invoke-PesterTests.ps1 -CI
    # Run all tests in CI mode (exits with error on failure)

.EXAMPLE
    .\Invoke-PesterTests.ps1 -TestPath "./scripts/tests"
    # Run only tests from scripts/tests directory

.EXAMPLE
    .\Invoke-PesterTests.ps1 -TestPath "./scripts/tests/Install-Common.Tests.ps1"
    # Run specific test file

.EXAMPLE
    .\Invoke-PesterTests.ps1 -Verbosity Diagnostic -PassThru
    # Run with maximum verbosity and return result object

.EXAMPLE
    .\Invoke-PesterTests.ps1 -EnableCodeCoverage
    # Run all tests with code coverage analysis (outputs to artifacts/TestResults/coverage.xml)

.EXAMPLE
    .\Invoke-PesterTests.ps1 -EnableCodeCoverage -CoverageFormat CoverageGutters
    # Run with code coverage in JSON format for VS Code CoverageGutters extension
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string[]]$TestPath = @("./scripts/tests", "./build/scripts/tests", "./build/tests", "./.claude/skills/*/tests", "./.github/scripts", "./.github/tests/**"),

    [Parameter()]
    [string]$OutputPath = "./artifacts/pester-results.xml",

    [Parameter()]
    [ValidateSet("NUnitXml", "JUnitXml")]
    [string]$OutputFormat = "JUnitXml",

    [Parameter()]
    [ValidateSet("None", "Normal", "Detailed", "Diagnostic")]
    [string]$Verbosity = "Detailed",

    [Parameter()]
    [switch]$CI,

    [Parameter()]
    [switch]$PassThru,

    [Parameter()]
    [switch]$EnableCodeCoverage,

    [Parameter()]
    [string]$CoverageOutputPath = "./artifacts/TestResults/coverage.xml",

    [Parameter()]
    [ValidateSet("JaCoCo", "CoverageGutters")]
    [string]$CoverageFormat = "JaCoCo",

    [Parameter()]
    [switch]$CheckCoverageThreshold
)

$ErrorActionPreference = "Stop"

# Disable ANSI color codes in CI mode to prevent XML corruption
# ANSI escape codes (0x1B) are invalid in XML and cause test-reporter to fail
if ($CI) {
    $env:NO_COLOR = '1'
    if ($PSVersionTable.PSVersion.Major -ge 7) {
        $PSStyle.OutputRendering = 'PlainText'
    }
    # Also set TERM to dumb to signal to scripts not to use colors
    $env:TERM = 'dumb'
}

# Resolve paths relative to repository root
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

# Resolve all test paths (expand wildcards and convert to absolute paths)
$ResolvedTestPaths = @()
foreach ($path in $TestPath) {
    # Normalize path separators and remove leading ./ or .\
    $cleanPath = $path -replace '^\.[\\/]', ''
    $fullPath = Join-Path $RepoRoot $cleanPath
    
    # Expand wildcards
    if ($fullPath -like "*[*]*" -or $fullPath -like "*[?]*") {
        $expanded = Get-Item -Path $fullPath -ErrorAction SilentlyContinue
        if ($expanded) {
            $ResolvedTestPaths += $expanded.FullName
        }
    }
    elseif (Test-Path $fullPath) {
        $ResolvedTestPaths += $fullPath
    }
}

# Filter to only existing paths
$TestPath = $ResolvedTestPaths | Where-Object { Test-Path $_ }
$OutputPath = Join-Path $RepoRoot ($OutputPath -replace '^\.[\\/]', '')
$CoverageOutputPath = Join-Path $RepoRoot ($CoverageOutputPath -replace '^\.[\\/]', '')

Write-Host ""
Write-Host "=== Pester Test Runner ===" -ForegroundColor Cyan
Write-Host "Repository Root: $RepoRoot"
Write-Host "Test Paths:"
foreach ($path in $TestPath) {
    Write-Host "  - $path" -ForegroundColor Gray
}
Write-Host "Output Path: $OutputPath"
Write-Host "Output Format: $OutputFormat"
Write-Host "Verbosity: $Verbosity"
Write-Host "CI Mode: $CI"
if ($EnableCodeCoverage) {
    Write-Host "Code Coverage: Enabled" -ForegroundColor Green
    Write-Host "Coverage Output: $CoverageOutputPath"
    Write-Host "Coverage Format: $CoverageFormat"
    if ($CheckCoverageThreshold) {
        Write-Host "Coverage Threshold Check: Enabled" -ForegroundColor Green
    }
}
Write-Host ""

# Verify Pester is installed - pin to specific version for supply chain security (issue #304)
$requiredPesterVersion = [version]"5.7.1"
$pester = Get-Module -ListAvailable -Name Pester | Where-Object { $_.Version -eq $requiredPesterVersion } | Select-Object -First 1
if (-not $pester) {
    Write-Host "Pester $requiredPesterVersion not found. Installing..." -ForegroundColor Yellow
    try {
        Set-PSRepository -Name 'PSGallery' -InstallationPolicy Trusted
        Install-Module -Name Pester -RequiredVersion $requiredPesterVersion -Force -Scope CurrentUser
    }
    catch {
        Write-Error "Failed to install required Pester version '$requiredPesterVersion': $_"
        throw
    }
}
# Import the module regardless of whether it was just installed or already present
try {
    Import-Module Pester -RequiredVersion $requiredPesterVersion -Force -ErrorAction Stop
    $pester = Get-Module Pester
    Write-Host "Using Pester version: $($pester.Version)" -ForegroundColor Green
}
catch {
    Write-Error "Failed to import Pester version '$requiredPesterVersion': $_"
    throw
}

# Verify at least one test path exists
if ($TestPath.Count -eq 0) {
    Write-Error "No test paths found or all test paths are invalid"
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

# Configure code coverage if enabled
if ($EnableCodeCoverage) {
    $config.CodeCoverage.Enabled = $true
    $config.CodeCoverage.OutputFormat = $CoverageFormat
    $config.CodeCoverage.OutputPath = $CoverageOutputPath

    # Analyze all PowerShell files in the test paths and their parent directories
    # This covers the scripts being tested (not just the test files themselves)
    $coveragePaths = @()
    foreach ($path in $TestPath) {
        if (Test-Path $path -PathType Container) {
            # If it's a test directory, analyze the parent directory for source files
            $parentDir = Split-Path -Parent $path
            $sourceFiles = Get-ChildItem -Path $parentDir -Filter "*.ps1" -Recurse -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -notlike "*.Tests.ps1" } |
                Select-Object -ExpandProperty FullName
            $coveragePaths += $sourceFiles
        }
        else {
            # If it's a specific test file, find the corresponding source file
            # Test file patterns:
            # - scripts/tests/Install-Common.Tests.ps1 -> scripts/Install-Common.ps1
            # - .claude/skills/github/tests/Foo.Tests.ps1 -> .claude/skills/github/scripts/Foo.ps1

            $testFileName = Split-Path -Leaf $path
            $sourceFileName = $testFileName -replace '\.Tests\.ps1$', '.ps1'

            # Get the test directory (e.g., "build/tests" or ".claude/skills/github/tests")
            $testDir = Split-Path -Parent $path

            # Determine source directory based on test directory pattern
            $sourceDir = $null
            if ($testDir -match '[\\/]tests$') {
                # Parent of tests directory (e.g., build/tests -> build, scripts/tests -> scripts)
                $parentDir = Split-Path -Parent $testDir
                $sourceDir = $parentDir

                # Special case for skills: tests -> scripts
                if ($testDir -match '[\\/]\.claude[\\/]skills[\\/].*[\\/]tests$') {
                    $sourceDir = Join-Path $parentDir "scripts"
                }
            }
            else {
                # Test file not in a tests directory, assume same directory
                $sourceDir = $testDir
            }

            # Try to find the source file
            if ($sourceDir -and (Test-Path $sourceDir -PathType Container)) {
                $sourceFile = Join-Path $sourceDir $sourceFileName
                if (Test-Path $sourceFile) {
                    $coveragePaths += $sourceFile
                }
                else {
                    # Also check subdirectories (e.g., build/scripts/Foo.ps1)
                    $sourceFiles = Get-ChildItem -Path $sourceDir -Filter $sourceFileName -Recurse -ErrorAction SilentlyContinue |
                        Select-Object -ExpandProperty FullName
                    $coveragePaths += $sourceFiles
                }
            }
        }
    }

    # Remove duplicates and set coverage paths
    $coveragePaths = $coveragePaths | Select-Object -Unique | Where-Object { $_ -and (Test-Path $_) }
    if ($coveragePaths.Count -gt 0) {
        $config.CodeCoverage.Path = $coveragePaths
        Write-Host "Code Coverage Paths ($($coveragePaths.Count) files):" -ForegroundColor Cyan
        foreach ($coveragePath in $coveragePaths) {
            $relativePath = [System.IO.Path]::GetRelativePath($RepoRoot, $coveragePath)
            Write-Host "  - $relativePath" -ForegroundColor Gray
        }
        Write-Host ""
    }
    else {
        Write-Host "Warning: No source files found for coverage analysis" -ForegroundColor Yellow
        Write-Host ""
    }
}

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

# Display code coverage summary if enabled
if ($EnableCodeCoverage -and $result.CodeCoverage) {
    Write-Host ""
    Write-Host "=== Code Coverage Summary ===" -ForegroundColor Cyan

    # Pester 5.x CodeCoverage object structure
    $coverage = $result.CodeCoverage

    # Try different property names (Pester versions may vary)
    $totalCommands = if ($coverage.PSObject.Properties['NumberOfCommandsAnalyzed']) {
        $coverage.NumberOfCommandsAnalyzed
    } elseif ($coverage.PSObject.Properties['CommandsAnalyzedCount']) {
        $coverage.CommandsAnalyzedCount
    } else {
        0
    }

    $executedCommands = if ($coverage.PSObject.Properties['NumberOfCommandsExecuted']) {
        $coverage.NumberOfCommandsExecuted
    } elseif ($coverage.PSObject.Properties['CommandsExecutedCount']) {
        $coverage.CommandsExecutedCount
    } elseif ($coverage.PSObject.Properties['CoveredCommands']) {
        $coverage.CoveredCommands.Count
    } else {
        0
    }

    $missedCommands = if ($coverage.PSObject.Properties['NumberOfCommandsMissed']) {
        $coverage.NumberOfCommandsMissed
    } elseif ($coverage.PSObject.Properties['CommandsMissedCount']) {
        $coverage.CommandsMissedCount
    } elseif ($coverage.PSObject.Properties['MissedCommands']) {
        $coverage.MissedCommands.Count
    } else {
        $totalCommands - $executedCommands
    }

    $coveragePercent = if ($totalCommands -gt 0) {
        [math]::Round(($executedCommands / $totalCommands) * 100, 2)
    } else { 0 }

    # Fallback: If we still have 0, it means the object structure is different
    # Just note that coverage was generated and saved to file
    if ($totalCommands -eq 0 -and (Test-Path $CoverageOutputPath)) {
        Write-Host "Coverage report generated successfully"
        Write-Host "View detailed coverage in: $CoverageOutputPath"
    } else {
        Write-Host "Commands Analyzed: $totalCommands"
        Write-Host "Commands Executed: $executedCommands"
        Write-Host "Commands Missed: $missedCommands"
        Write-Host "Coverage: $coveragePercent%" -ForegroundColor $(if ($coveragePercent -ge 80) { "Green" } elseif ($coveragePercent -ge 60) { "Yellow" } else { "Red" })
    }
}

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
if ($EnableCodeCoverage) {
    Write-Host "Coverage report saved to: $CoverageOutputPath"
}

# Check coverage against baseline thresholds
if ($EnableCodeCoverage -and $CheckCoverageThreshold -and $result.CodeCoverage) {
    Write-Host ""
    Write-Host "=== Coverage Threshold Check ===" -ForegroundColor Cyan

    $thresholdsFile = Join-Path $RepoRoot ".baseline" "coverage-thresholds.json"

    if (-not (Test-Path $thresholdsFile)) {
        Write-Host "Warning: Coverage thresholds file not found at: $thresholdsFile" -ForegroundColor Yellow
        Write-Host "Skipping threshold check." -ForegroundColor Yellow
    }
    else {
        $thresholds = Get-Content $thresholdsFile | ConvertFrom-Json

        # Check coverage for each test path
        $coverageFailures = @()

        foreach ($path in $TestPath) {
            # Get relative path for lookup
            $relativePath = [System.IO.Path]::GetRelativePath($RepoRoot, $path) -replace '\\', '/'

            # Check if this test has a threshold
            $threshold = $thresholds.thresholds.$relativePath

            if ($threshold) {
                # Use the same coverage calculation as the summary section
                # (Coverage was already calculated earlier in the script)
                $coverage = $result.CodeCoverage

                # Try different property names (Pester versions may vary)
                $totalCommands = if ($coverage.PSObject.Properties['NumberOfCommandsAnalyzed']) {
                    $coverage.NumberOfCommandsAnalyzed
                } elseif ($coverage.PSObject.Properties['CommandsAnalyzedCount']) {
                    $coverage.CommandsAnalyzedCount
                } else {
                    0
                }

                $executedCommands = if ($coverage.PSObject.Properties['NumberOfCommandsExecuted']) {
                    $coverage.NumberOfCommandsExecuted
                } elseif ($coverage.PSObject.Properties['CommandsExecutedCount']) {
                    $coverage.CommandsExecutedCount
                } elseif ($coverage.PSObject.Properties['CoveredCommands']) {
                    $coverage.CoveredCommands.Count
                } else {
                    0
                }

                $actualCoverage = if ($totalCommands -gt 0) {
                    [math]::Round(($executedCommands / $totalCommands) * 100, 2)
                } else { 0 }

                $minCoverage = $threshold.minCoverage

                Write-Host ""
                Write-Host "Test: $relativePath" -ForegroundColor Cyan
                Write-Host "  Minimum Required: $minCoverage%"
                Write-Host "  Actual Coverage: $actualCoverage%"

                if ($actualCoverage -lt $minCoverage) {
                    $deficit = [math]::Round($minCoverage - $actualCoverage, 2)
                    Write-Host "  Status: FAILED" -ForegroundColor Red
                    Write-Host "  Deficit: -$deficit%" -ForegroundColor Red
                    $coverageFailures += @{
                        Path = $relativePath
                        Required = $minCoverage
                        Actual = $actualCoverage
                        Deficit = $deficit
                    }
                }
                else {
                    $surplus = [math]::Round($actualCoverage - $minCoverage, 2)
                    Write-Host "  Status: PASSED" -ForegroundColor Green
                    if ($surplus -gt 0) {
                        Write-Host "  Surplus: +$surplus%" -ForegroundColor Green
                    }
                }
            }
        }

        Write-Host ""

        if ($coverageFailures.Count -gt 0) {
            Write-Host "COVERAGE REGRESSION DETECTED:" -ForegroundColor Red
            Write-Host "$($coverageFailures.Count) test(s) fell below coverage threshold" -ForegroundColor Red
            Write-Host ""
            foreach ($failure in $coverageFailures) {
                Write-Host "  - $($failure.Path): $($failure.Actual)% (required: $($failure.Required)%, deficit: -$($failure.Deficit)%)" -ForegroundColor Red
            }
            Write-Host ""

            if ($CI) {
                Write-Error "Code coverage regression detected. Build failed."
                exit 1
            }
            else {
                Write-Host "To fix:" -ForegroundColor Yellow
                Write-Host "  1. Add more tests to increase coverage" -ForegroundColor Yellow
                Write-Host "  2. If intentional, update thresholds in .baseline/coverage-thresholds.json" -ForegroundColor Yellow
                Write-Host ""
                Write-Error "Code coverage regression detected."
                exit 1
            }
        }
        else {
            Write-Host "All coverage thresholds met" -ForegroundColor Green
        }
    }
}

# Return result object if requested
if ($PassThru) {
    return $result
}

# Exit with appropriate code for local runs
if (-not $CI -and $result.FailedCount -gt 0) {
    exit 1
}
