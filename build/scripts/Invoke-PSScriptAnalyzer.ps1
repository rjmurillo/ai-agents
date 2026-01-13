<#
.SYNOPSIS
    Runs PSScriptAnalyzer on PowerShell scripts in the repository.

.DESCRIPTION
    Performs static analysis on all .ps1 and .psm1 files using PSScriptAnalyzer.
    Designed for both CI/CD and local development use.

    This script is called by:
    - .github/workflows/pester-tests.yml (CI/CD)
    - Local developers validating scripts manually
    - Pre-commit hooks for early validation

.PARAMETER Path
    Root path to scan for PowerShell files.
    Defaults to current directory.

.PARAMETER OutputPath
    Path for analysis results output file.
    Defaults to ./artifacts/psscriptanalyzer-results.xml

.PARAMETER ExcludePaths
    Array of path patterns to exclude from analysis.
    Defaults to common exclusions like node_modules, .git, etc.

.PARAMETER Severity
    Minimum severity level to report.
    Valid values: Information, Warning, Error
    Defaults to Warning (reports Warning and Error).

.PARAMETER FailOnError
    If specified, exit with error code when Error-level issues found.
    Defaults to true in CI mode.

.PARAMETER CI
    Run in CI mode (stricter settings, machine-readable output).
    Enables FailOnError by default.

.PARAMETER PassThru
    Return the analysis results object for programmatic access.

.EXAMPLE
    .\Invoke-PSScriptAnalyzer.ps1
    # Analyze all PowerShell files in repository

.EXAMPLE
    .\Invoke-PSScriptAnalyzer.ps1 -CI
    # Run in CI mode (fails on errors)

.EXAMPLE
    .\Invoke-PSScriptAnalyzer.ps1 -Severity Error -FailOnError
    # Only report errors and fail if any found

.NOTES
    Exit Codes:
    0 - Success (no errors, or only warnings/info if -Severity allows)
    1 - Error-level issues found (when -FailOnError)
    2 - Script execution error
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Path = ".",

    [Parameter()]
    [string]$OutputPath = "./artifacts/psscriptanalyzer-results.xml",

    [Parameter()]
    [string[]]$ExcludePaths = @(
        "**/node_modules/**",
        "**/.git/**",
        "**/artifacts/**",
        "**/.serena/**"
    ),

    [Parameter()]
    [ValidateSet("Information", "Warning", "Error")]
    [string]$Severity = "Warning",

    [Parameter()]
    [switch]$FailOnError,

    [Parameter()]
    [switch]$CI,

    [Parameter()]
    [switch]$PassThru
)

# Set strict mode for better error detection
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# CI mode enables FailOnError by default
if ($CI) {
    $FailOnError = $true
}

# Ensure PSScriptAnalyzer is available
if (-not (Get-Module -ListAvailable -Name PSScriptAnalyzer)) {
    Write-Host "Installing PSScriptAnalyzer module..." -ForegroundColor Cyan
    Install-Module -Name PSScriptAnalyzer -Force -Scope CurrentUser -AllowClobber
}

Import-Module PSScriptAnalyzer -Force

# Resolve to absolute path
$Path = Resolve-Path $Path | Select-Object -ExpandProperty Path

Write-Host "Scanning for PowerShell files in: $Path" -ForegroundColor Cyan

# Find all PowerShell files (wrap in @() to ensure array type)
$files = @(Get-ChildItem -Path $Path -Recurse -Include "*.ps1", "*.psm1" -File)

# Apply exclusions (convert glob patterns to PowerShell-compatible patterns)
$originalCount = $files.Count
foreach ($excludePattern in $ExcludePaths) {
    # Convert glob patterns: ** -> * (PowerShell -like supports * for any chars)
    $psPattern = $excludePattern -replace '\*\*/', '*' -replace '\*\*', '*'
    $files = @($files | Where-Object {
        $relativePath = $_.FullName.Replace($Path, "").TrimStart([System.IO.Path]::DirectorySeparatorChar)
        # Also check with forward slashes for cross-platform compatibility
        $relativePathNormalized = $relativePath -replace '\\', '/'
        -not (($relativePath -like $psPattern) -or ($relativePathNormalized -like $psPattern))
    })
}

Write-Host "Found $($files.Count) PowerShell files to analyze (excluded $($originalCount - $files.Count) files)" -ForegroundColor Cyan

if ($files.Count -eq 0) {
    Write-Host "No PowerShell files found to analyze." -ForegroundColor Yellow
    if ($PassThru) {
        return @{
            TotalFiles = 0
            TotalIssues = 0
            ErrorCount = 0
            WarningCount = 0
            InformationCount = 0
            Results = @()
        }
    }
    exit 0
}

# Determine severity filter
$severityFilter = switch ($Severity) {
    "Error" { @("Error") }
    "Warning" { @("Warning", "Error") }
    "Information" { @("Information", "Warning", "Error") }
}

# Run PSScriptAnalyzer on each file and collect results
$allResults = [System.Collections.Generic.List[object]]::new()

foreach ($file in $files) {
    Write-Verbose "Analyzing: $($file.FullName)"

    try {
        $results = Invoke-ScriptAnalyzer -Path $file.FullName -Severity $severityFilter -ErrorAction Stop

        foreach ($result in $results) {
            $allResults.Add([PSCustomObject]@{
                FilePath    = $file.FullName
                RelativePath = $file.FullName.Replace($Path, "").TrimStart([System.IO.Path]::DirectorySeparatorChar)
                Line        = $result.Line
                Column      = $result.Column
                Severity    = $result.Severity.ToString()
                RuleName    = $result.RuleName
                Message     = $result.Message
            })
        }
    }
    catch {
        Write-Warning "Failed to analyze $($file.FullName): $($_.Exception.Message)"
    }
}

# Count by severity
$errorCount = @($allResults | Where-Object { $_.Severity -eq "Error" }).Count
$warningCount = @($allResults | Where-Object { $_.Severity -eq "Warning" }).Count
$informationCount = @($allResults | Where-Object { $_.Severity -eq "Information" }).Count

# Summary
Write-Host ""
Write-Host "=== PSScriptAnalyzer Results ===" -ForegroundColor Cyan
Write-Host "Files analyzed: $($files.Count)" -ForegroundColor White
Write-Host "Total issues: $($allResults.Count)" -ForegroundColor White
if ($errorCount -gt 0) {
    Write-Host "  Errors: $errorCount" -ForegroundColor Red
}
if ($warningCount -gt 0) {
    Write-Host "  Warnings: $warningCount" -ForegroundColor Yellow
}
if ($informationCount -gt 0) {
    Write-Host "  Information: $informationCount" -ForegroundColor Gray
}

# Output detailed results
if ($allResults.Count -gt 0) {
    Write-Host ""
    Write-Host "=== Issues Found ===" -ForegroundColor Cyan

    foreach ($result in $allResults) {
        $color = switch ($result.Severity) {
            "Error" { "Red" }
            "Warning" { "Yellow" }
            default { "Gray" }
        }

        Write-Host "[$($result.Severity)] $($result.RelativePath):$($result.Line):$($result.Column)" -ForegroundColor $color
        Write-Host "  Rule: $($result.RuleName)" -ForegroundColor $color
        Write-Host "  $($result.Message)" -ForegroundColor White
        Write-Host ""
    }
}

# Ensure output directory exists
$outputDir = Split-Path $OutputPath -Parent
if ($outputDir -and -not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

# Export to XML for CI integration
$xmlResults = [xml]"<?xml version='1.0' encoding='utf-8'?><testsuites></testsuites>"
$testsuitesNode = $xmlResults.SelectSingleNode("//testsuites")

$testsuite = $xmlResults.CreateElement("testsuite")
$testsuite.SetAttribute("name", "PSScriptAnalyzer")
$testsuite.SetAttribute("tests", $files.Count.ToString())
$testsuite.SetAttribute("failures", $errorCount.ToString())
$testsuite.SetAttribute("warnings", $warningCount.ToString())

foreach ($result in $allResults) {
    $testcase = $xmlResults.CreateElement("testcase")
    $testcase.SetAttribute("name", "$($result.RelativePath):$($result.Line) - $($result.RuleName)")
    $testcase.SetAttribute("classname", $result.RuleName)

    if ($result.Severity -eq "Error") {
        $failure = $xmlResults.CreateElement("failure")
        $failure.SetAttribute("message", $result.Message)
        $failure.SetAttribute("type", $result.RuleName)
        $failure.InnerText = "File: $($result.FilePath)`nLine: $($result.Line), Column: $($result.Column)`nRule: $($result.RuleName)`nMessage: $($result.Message)"
        $testcase.AppendChild($failure) | Out-Null
    }
    elseif ($result.Severity -eq "Warning") {
        $systemOut = $xmlResults.CreateElement("system-out")
        $systemOut.InnerText = "[Warning] $($result.Message)"
        $testcase.AppendChild($systemOut) | Out-Null
    }

    $testsuite.AppendChild($testcase) | Out-Null
}

$testsuitesNode.AppendChild($testsuite) | Out-Null
$xmlResults.Save($OutputPath)

Write-Host ""
Write-Host "Results saved to: $OutputPath" -ForegroundColor Cyan

# Return results object if requested
if ($PassThru) {
    return [PSCustomObject]@{
        TotalFiles       = $files.Count
        TotalIssues      = $allResults.Count
        ErrorCount       = $errorCount
        WarningCount     = $warningCount
        InformationCount = $informationCount
        Results          = $allResults
    }
}

# Exit with error if errors found and FailOnError is set
if ($FailOnError -and $errorCount -gt 0) {
    Write-Host ""
    Write-Host "Build failed: $errorCount Error-level issue(s) found" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "PSScriptAnalyzer validation completed successfully" -ForegroundColor Green
exit 0
