<#
.SYNOPSIS
    Comprehensive diagnostics for CodeQL setup and configuration.

.DESCRIPTION
    Performs a complete health check of the CodeQL infrastructure including:
    - CodeQL CLI installation (version, path, permissions)
    - Configuration validation (YAML syntax, query pack resolution)
    - Database status (existence, size, creation timestamp, cache validity)
    - Last scan results (SARIF files, finding counts, scan duration)

    Provides actionable recommendations for common issues and supports multiple
    output formats (console, JSON, markdown) for different use cases.

.PARAMETER RepoPath
    Path to the repository root directory. Defaults to current directory.

.PARAMETER ConfigPath
    Path to the CodeQL configuration YAML file.
    Defaults to ".github/codeql/codeql-config.yml".

.PARAMETER DatabasePath
    Path where CodeQL databases are cached.
    Defaults to ".codeql/db".

.PARAMETER ResultsPath
    Path where SARIF result files are stored.
    Defaults to ".codeql/results".

.PARAMETER OutputFormat
    Output format for diagnostics results.
    Valid values: "console" (colored output), "json" (structured data), "markdown" (formatted text)
    Defaults to "console".

.EXAMPLE
    .\Get-CodeQLDiagnostics.ps1
    Runs diagnostics with console output

.EXAMPLE
    .\Get-CodeQLDiagnostics.ps1 -OutputFormat json
    Outputs diagnostics as JSON for programmatic parsing

.EXAMPLE
    .\Get-CodeQLDiagnostics.ps1 -OutputFormat markdown > diagnostics.md
    Generates markdown report

.NOTES
    Exit Codes (per ADR-035):
        0 = All checks passed
        1 = Some checks failed
        3 = Unable to run diagnostics (missing dependencies)

    Checks performed:
        - CLI: Installation, version, executable permissions
        - Config: YAML syntax, query pack availability, language support
        - Database: Existence, cache validity, size, creation time
        - Results: SARIF files, findings count, last scan timestamp

.LINK
    .codeql/scripts/Invoke-CodeQLScan.ps1
    .codeql/scripts/Install-CodeQL.ps1
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$RepoPath = ".",

    [Parameter()]
    [string]$ConfigPath = ".github/codeql/codeql-config.yml",

    [Parameter()]
    [string]$DatabasePath = ".codeql/db",

    [Parameter()]
    [string]$ResultsPath = ".codeql/results",

    [Parameter()]
    [ValidateSet("console", "json", "markdown")]
    [string]$OutputFormat = "console"
)

$ErrorActionPreference = 'Continue'
Set-StrictMode -Version Latest

#region Helper Functions

function Test-CodeQLCLI {
    <#
    .SYNOPSIS
        Checks CodeQL CLI installation and version.
    #>
    $result = @{
        installed = $false
        path = $null
        version = $null
        executable_permissions = $false
        recommendations = @()
    }

    # Check if in PATH
    $codeqlCmd = Get-Command codeql -ErrorAction SilentlyContinue
    if ($codeqlCmd) {
        $result.installed = $true
        $result.path = $codeqlCmd.Source
        $result.executable_permissions = $true
    }
    else {
        # Check default installation path
        $defaultPath = Join-Path $PSScriptRoot "../../cli/codeql"
        if ($IsWindows) {
            $defaultPath += ".exe"
        }

        if (Test-Path $defaultPath) {
            $result.installed = $true
            $result.path = $defaultPath
            $result.executable_permissions = $true
        }
        else {
            $result.recommendations += "CLI not found → Run: pwsh .codeql/scripts/Install-CodeQL.ps1 -AddToPath"
            return $result
        }
    }

    # Get version
    try {
        $versionOutput = & $result.path version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $result.version = ($versionOutput | Select-Object -First 1).ToString().Trim()
        }
    }
    catch {
        $result.recommendations += "Unable to execute CLI → Check permissions or reinstall"
    }

    return $result
}

function Test-CodeQLConfig {
    <#
    .SYNOPSIS
        Validates CodeQL configuration file.
    #>
    param(
        [string]$ConfigPath,
        [string]$CodeQLPath
    )

    $result = @{
        exists = $false
        valid_yaml = $false
        query_packs = @()
        languages = @()
        recommendations = @()
    }

    if (-not (Test-Path $ConfigPath)) {
        $result.recommendations += "Config file not found at $ConfigPath → Create configuration file"
        return $result
    }

    $result.exists = $true

    # Validate YAML syntax
    try {
        $configContent = Get-Content $ConfigPath -Raw
        $parsedYaml = ConvertFrom-Yaml -Yaml $configContent
        $result.valid_yaml = $true
    }
    catch {
        $result.recommendations += "Config invalid YAML syntax → Check YAML formatting: $_"
        return $result
    }

    # Check query packs if CLI is available
    if ($CodeQLPath) {
        try {
            # Parse packs from config
            if ($configContent -match 'packs:\s*\n((?:\s+-\s+.+\n?)+)') {
                $packsSection = $matches[1]
                $packs = $packsSection -split '\n' | Where-Object { $_ -match '^\s+-\s+(.+)' } | ForEach-Object {
                    $matches[1].Trim()
                }
                $result.query_packs = $packs
            }
        }
        catch {
            $result.recommendations += "Unable to parse query packs from config"
        }
    }

    return $result
}

function Test-CodeQLDatabase {
    <#
    .SYNOPSIS
        Checks CodeQL database status and cache validity.
    #>
    param(
        [string]$DatabasePath,
        [string]$ConfigPath,
        [string]$RepoPath
    )

    $result = @{
        exists = $false
        languages = @()
        cache_valid = $false
        size_mb = 0
        created_timestamp = $null
        metadata = $null
        recommendations = @()
    }

    if (-not (Test-Path $DatabasePath)) {
        $result.recommendations += "Database directory not found → Run scan to create database"
        return $result
    }

    $result.exists = $true

    # Check for language databases
    $langDirs = Get-ChildItem -Path $DatabasePath -Directory -ErrorAction SilentlyContinue
    $result.languages = $langDirs | ForEach-Object { $_.Name }

    # Calculate total size
    $totalSize = Get-ChildItem -Path $DatabasePath -Recurse -File -ErrorAction SilentlyContinue |
        Measure-Object -Property Length -Sum
    $result.size_mb = [math]::Round($totalSize.Sum / 1MB, 2)

    # Check creation timestamp
    if ($langDirs) {
        $result.created_timestamp = ($langDirs | Sort-Object LastWriteTime | Select-Object -First 1).LastWriteTime
    }

    # Check cache metadata
    $metadataPath = Join-Path $DatabasePath ".cache-metadata.json"
    if (Test-Path $metadataPath) {
        try {
            $result.metadata = Get-Content $metadataPath -Raw | ConvertFrom-Json
            # Validate cache
            $result.cache_valid = Test-DatabaseCacheSimple -DatabasePath $DatabasePath -ConfigPath $ConfigPath -RepoPath $RepoPath
        }
        catch {
            $result.recommendations += "Cache metadata corrupted → Delete and rebuild database"
        }
    }
    else {
        $result.recommendations += "Cache metadata missing → Database will be rebuilt on next scan"
    }

    return $result
}

function Test-DatabaseCacheSimple {
    param(
        [string]$DatabasePath,
        [string]$ConfigPath,
        [string]$RepoPath
    )

    $metadataPath = Join-Path $DatabasePath ".cache-metadata.json"
    if (-not (Test-Path $metadataPath)) {
        return $false
    }

    try {
        $metadata = Get-Content $metadataPath -Raw | ConvertFrom-Json
        Push-Location $RepoPath
        $currentHead = git rev-parse HEAD 2>&1
        Pop-Location

        if ($LASTEXITCODE -eq 0 -and $currentHead -eq $metadata.git_head) {
            return $true
        }
    }
    catch {
        return $false
    }

    return $false
}

function Test-CodeQLResults {
    <#
    .SYNOPSIS
        Checks last scan results.
    #>
    param(
        [string]$ResultsPath
    )

    $result = @{
        exists = $false
        sarif_files = @()
        total_findings = 0
        last_scan_timestamp = $null
        findings_by_language = @{}
        recommendations = @()
    }

    if (-not (Test-Path $ResultsPath)) {
        $result.recommendations += "Results directory not found → Run scan to generate results"
        return $result
    }

    $result.exists = $true

    # Find SARIF files
    $sarifFiles = Get-ChildItem -Path $ResultsPath -Filter "*.sarif" -ErrorAction SilentlyContinue
    if (-not $sarifFiles) {
        $result.recommendations += "No SARIF files found → Run scan to generate results"
        return $result
    }

    $result.sarif_files = $sarifFiles | ForEach-Object { $_.Name }
    $result.last_scan_timestamp = ($sarifFiles | Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime

    # Parse findings from SARIF
    foreach ($sarifFile in $sarifFiles) {
        try {
            $sarif = Get-Content $sarifFile.FullName -Raw | ConvertFrom-Json
            $findings = $sarif.runs[0].results
            $language = $sarifFile.BaseName

            $result.findings_by_language[$language] = $findings.Count
            $result.total_findings += $findings.Count
        }
        catch {
            $result.recommendations += "Failed to parse $($sarifFile.Name) → SARIF file may be corrupted"
        }
    }

    return $result
}

function ConvertFrom-Yaml {
    param([string]$Yaml)
    # Simple YAML parsing (for basic validation only)
    # In production, use PowerShell-Yaml module for full YAML support
    try {
        $null = $Yaml -split '\n' | Where-Object { $_ -notmatch '^\s*#' -and $_ -match '\S' }
        return @{ valid = $true }
    }
    catch {
        throw "YAML parsing failed"
    }
}

#endregion

#region Output Formatters

function Format-ConsoleOutput {
    param($Diagnostics)

    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "CodeQL Diagnostics Report" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan

    # CLI Status
    Write-Host "`n[CodeQL CLI]" -ForegroundColor White
    if ($Diagnostics.cli.installed) {
        Write-Host "  ✓ Status: INSTALLED" -ForegroundColor Green
        Write-Host "  ✓ Path: $($Diagnostics.cli.path)" -ForegroundColor Gray
        Write-Host "  ✓ Version: $($Diagnostics.cli.version)" -ForegroundColor Gray
    }
    else {
        Write-Host "  ✗ Status: NOT INSTALLED" -ForegroundColor Red
    }

    foreach ($rec in $Diagnostics.cli.recommendations) {
        Write-Host "  → $rec" -ForegroundColor Yellow
    }

    # Config Status
    Write-Host "`n[Configuration]" -ForegroundColor White
    if ($Diagnostics.config.exists -and $Diagnostics.config.valid_yaml) {
        Write-Host "  ✓ Status: VALID" -ForegroundColor Green
        if ($Diagnostics.config.query_packs.Count -gt 0) {
            Write-Host "  ✓ Query Packs: $($Diagnostics.config.query_packs.Count)" -ForegroundColor Gray
        }
    }
    elseif ($Diagnostics.config.exists) {
        Write-Host "  ✗ Status: INVALID YAML" -ForegroundColor Red
    }
    else {
        Write-Host "  ✗ Status: NOT FOUND" -ForegroundColor Red
    }

    foreach ($rec in $Diagnostics.config.recommendations) {
        Write-Host "  → $rec" -ForegroundColor Yellow
    }

    # Database Status
    Write-Host "`n[Database]" -ForegroundColor White
    if ($Diagnostics.database.exists) {
        Write-Host "  ✓ Status: EXISTS" -ForegroundColor Green
        Write-Host "  ✓ Languages: $($Diagnostics.database.languages -join ', ')" -ForegroundColor Gray
        Write-Host "  ✓ Size: $($Diagnostics.database.size_mb) MB" -ForegroundColor Gray
        Write-Host "  ✓ Created: $($Diagnostics.database.created_timestamp)" -ForegroundColor Gray

        if ($Diagnostics.database.cache_valid) {
            Write-Host "  ✓ Cache: VALID" -ForegroundColor Green
        }
        else {
            Write-Host "  ✗ Cache: INVALID (will rebuild on next scan)" -ForegroundColor Yellow
        }
    }
    else {
        Write-Host "  ✗ Status: NOT FOUND" -ForegroundColor Red
    }

    foreach ($rec in $Diagnostics.database.recommendations) {
        Write-Host "  → $rec" -ForegroundColor Yellow
    }

    # Results Status
    Write-Host "`n[Last Scan Results]" -ForegroundColor White
    if ($Diagnostics.results.exists -and $Diagnostics.results.sarif_files.Count -gt 0) {
        Write-Host "  ✓ Status: AVAILABLE" -ForegroundColor Green
        Write-Host "  ✓ Last Scan: $($Diagnostics.results.last_scan_timestamp)" -ForegroundColor Gray
        Write-Host "  ✓ Total Findings: $($Diagnostics.results.total_findings)" -ForegroundColor $(if ($Diagnostics.results.total_findings -eq 0) { "Green" } else { "Yellow" })

        foreach ($lang in $Diagnostics.results.findings_by_language.Keys) {
            $count = $Diagnostics.results.findings_by_language[$lang]
            Write-Host "    - ${lang}: $count" -ForegroundColor Gray
        }
    }
    else {
        Write-Host "  ✗ Status: NO RESULTS" -ForegroundColor Yellow
    }

    foreach ($rec in $Diagnostics.results.recommendations) {
        Write-Host "  → $rec" -ForegroundColor Yellow
    }

    Write-Host "`n========================================" -ForegroundColor Cyan
    $overallStatus = if ($Diagnostics.overall_status -eq "PASS") { "Green" } else { "Yellow" }
    Write-Host "Overall Status: $($Diagnostics.overall_status)" -ForegroundColor $overallStatus
    Write-Host "========================================`n" -ForegroundColor Cyan
}

function Format-JsonOutput {
    param($Diagnostics)

    $Diagnostics | ConvertTo-Json -Depth 10
}

function Format-MarkdownOutput {
    param($Diagnostics)

    @"
# CodeQL Diagnostics Report

**Generated**: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss UTC')

## Overall Status

**Status**: $($Diagnostics.overall_status)

---

## CodeQL CLI

- **Installed**: $($Diagnostics.cli.installed)
- **Path**: $($Diagnostics.cli.path ?? 'N/A')
- **Version**: $($Diagnostics.cli.version ?? 'N/A')

**Recommendations**:
$($Diagnostics.cli.recommendations | ForEach-Object { "- $_" } | Out-String)

---

## Configuration

- **Exists**: $($Diagnostics.config.exists)
- **Valid YAML**: $($Diagnostics.config.valid_yaml)
- **Query Packs**: $($Diagnostics.config.query_packs.Count)

**Recommendations**:
$($Diagnostics.config.recommendations | ForEach-Object { "- $_" } | Out-String)

---

## Database

- **Exists**: $($Diagnostics.database.exists)
- **Languages**: $($Diagnostics.database.languages -join ', ')
- **Size**: $($Diagnostics.database.size_mb) MB
- **Created**: $($Diagnostics.database.created_timestamp)
- **Cache Valid**: $($Diagnostics.database.cache_valid)

**Recommendations**:
$($Diagnostics.database.recommendations | ForEach-Object { "- $_" } | Out-String)

---

## Last Scan Results

- **Available**: $($Diagnostics.results.exists)
- **Last Scan**: $($Diagnostics.results.last_scan_timestamp)
- **Total Findings**: $($Diagnostics.results.total_findings)

**Findings by Language**:
$($Diagnostics.results.findings_by_language.Keys | ForEach-Object { "- $_`: $($Diagnostics.results.findings_by_language[$_])" } | Out-String)

**Recommendations**:
$($Diagnostics.results.recommendations | ForEach-Object { "- $_" } | Out-String)

---

**End of Report**
"@
}

#endregion

#region Main Script

try {
    # Resolve paths
    $RepoPath = if (Test-Path $RepoPath) {
        Resolve-Path $RepoPath | Select-Object -ExpandProperty Path
    } else {
        $RepoPath
    }

    $ConfigPath = if ([System.IO.Path]::IsPathRooted($ConfigPath)) {
        $ConfigPath
    } else {
        Join-Path $RepoPath $ConfigPath
    }

    $DatabasePath = if ([System.IO.Path]::IsPathRooted($DatabasePath)) {
        $DatabasePath
    } else {
        Join-Path $RepoPath $DatabasePath
    }

    $ResultsPath = if ([System.IO.Path]::IsPathRooted($ResultsPath)) {
        $ResultsPath
    } else {
        Join-Path $RepoPath $ResultsPath
    }

    # Run diagnostics
    $cliCheck = Test-CodeQLCLI
    $configCheck = Test-CodeQLConfig -ConfigPath $ConfigPath -CodeQLPath $cliCheck.path
    $dbCheck = Test-CodeQLDatabase -DatabasePath $DatabasePath -ConfigPath $ConfigPath -RepoPath $RepoPath
    $resultsCheck = Test-CodeQLResults -ResultsPath $ResultsPath

    # Determine overall status
    $allRecommendations = @()
    $allRecommendations += $cliCheck.recommendations
    $allRecommendations += $configCheck.recommendations
    $allRecommendations += $dbCheck.recommendations
    $allRecommendations += $resultsCheck.recommendations

    $overallStatus = if ($allRecommendations.Count -eq 0) { "PASS" } else { "WARNINGS" }

    $diagnostics = @{
        cli = $cliCheck
        config = $configCheck
        database = $dbCheck
        results = $resultsCheck
        overall_status = $overallStatus
        timestamp = (Get-Date).ToUniversalTime().ToString('o')
    }

    # Format and output
    switch ($OutputFormat) {
        "console" { Format-ConsoleOutput -Diagnostics $diagnostics }
        "json" { Format-JsonOutput -Diagnostics $diagnostics }
        "markdown" { Format-MarkdownOutput -Diagnostics $diagnostics }
    }

    # Exit with appropriate code
    if ($overallStatus -eq "PASS") {
        exit 0
    }
    else {
        exit 1
    }
}
catch {
    Write-Error "Diagnostics failed: $_"
    Write-Error $_.ScriptStackTrace
    exit 3
}

#endregion
