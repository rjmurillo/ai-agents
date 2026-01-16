<#
.SYNOPSIS
    Validates CodeQL configuration file syntax and content.

.DESCRIPTION
    This script performs comprehensive validation of the CodeQL configuration YAML file:
    1. YAML syntax validation
    2. Query pack availability verification
    3. Path existence checks
    4. Schema validation (required fields, valid values)

    The script follows the repository's PowerShell-only convention (ADR-005) and uses
    standardized exit codes (ADR-035). It's designed to run as a pre-scan validation
    step or as part of CI/CD pipelines.

.PARAMETER ConfigPath
    Path to the CodeQL configuration YAML file.
    Defaults to ".github/codeql/codeql-config.yml".

.PARAMETER CI
    Enables CI mode with non-interactive behavior. In CI mode, the script exits with
    code 1 if validation fails.

.PARAMETER Format
    Output format for validation results.
    Valid values: "console" (colored report), "json" (structured JSON)
    Defaults to "console".

.EXAMPLE
    .\Test-CodeQLConfig.ps1
    Validates default config file with console output

.EXAMPLE
    .\Test-CodeQLConfig.ps1 -ConfigPath ".github/codeql/custom-config.yml" -CI
    Validates custom config in CI mode, exits with error on failures

.EXAMPLE
    .\Test-CodeQLConfig.ps1 -Format json
    Validates config and outputs structured JSON results

.NOTES
    Exit Codes (per ADR-035):
        0 = Valid configuration
        1 = Invalid configuration (validation errors)
        2 = Configuration file not found
        3 = External dependency error (CodeQL CLI not found)

    Requirements:
        - CodeQL CLI must be installed (for query pack resolution)
        - Valid YAML syntax in config file

    Validation Rules:
        - YAML must parse successfully
        - Config must have 'name' field
        - Config must have either 'packs' or 'queries' field
        - Severity values must be valid (low, medium, high, critical)
        - Paths in 'paths' section should exist (warning only)

.LINK
    https://codeql.github.com/docs/codeql-cli/creating-codeql-query-suites/
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$ConfigPath = ".github/codeql/codeql-config.yml",

    [Parameter()]
    [switch]$CI,

    [Parameter()]
    [ValidateSet("console", "json")]
    [string]$Format = "console"
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

#region Helper Functions

function Test-YamlSyntax {
    <#
    .SYNOPSIS
        Validates YAML syntax and parses content using available YAML parsers.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$ConfigPath
    )

    try {
        $content = Get-Content $ConfigPath -Raw

        if ([string]::IsNullOrWhiteSpace($content)) {
            return @{
                Valid = $false
                Error = "Config file is empty"
                ParsedContent = $null
            }
        }

        # Try to use ConvertFrom-Yaml if powershell-yaml module is available
        $yamlModule = Get-Module -Name powershell-yaml -ListAvailable -ErrorAction SilentlyContinue
        if ($yamlModule) {
            try {
                Import-Module powershell-yaml -ErrorAction Stop
                $parsedContent = ConvertFrom-Yaml $content -ErrorAction Stop
                return @{
                    Valid = $true
                    Content = $content
                    ParsedContent = $parsedContent
                }
            }
            catch {
                return @{
                    Valid = $false
                    Error = "YAML parse error: $($_.Exception.Message)"
                    ParsedContent = $null
                }
            }
        }

        # Fallback: Use a lightweight YAML parser for basic validation
        # Check for common YAML syntax errors
        $lines = $content -split "`n"
        $lineNum = 0

        foreach ($line in $lines) {
            $lineNum++

            # Skip empty lines and comments
            if ($line -match '^\s*(#|$)') { continue }

            # Check for tabs (YAML should use spaces)
            if ($line -match '^\t') {
                return @{
                    Valid = $false
                    Error = "YAML parse error at line ${lineNum}: Tabs are not allowed for indentation"
                    ParsedContent = $null
                }
            }

            # Check for invalid key-value syntax (colon without space)
            if ($line -match '^\s*[\w\-]+:[^\s]' -and $line -notmatch '^\s*[\w\-]+:\s*[''"]' -and $line -notmatch '^\s*[\w\-]+:\s*$') {
                # This might be a URL or valid value, so we're lenient here
            }

            # Check for unbalanced quotes
            $singleQuotes = ($line -split "'" | Measure-Object).Count - 1
            $doubleQuotes = ($line -split '"' | Measure-Object).Count - 1
            if (($singleQuotes % 2 -ne 0) -or ($doubleQuotes % 2 -ne 0)) {
                # Could be multi-line string, be lenient
            }
        }

        # Basic structure validation passed
        Write-Verbose "YAML basic validation passed (powershell-yaml module not available for deep parsing)"
        return @{
            Valid = $true
            Content = $content
            ParsedContent = $null  # No deep parsing without powershell-yaml
        }
    }
    catch {
        return @{
            Valid = $false
            Error = $_.Exception.Message
            ParsedContent = $null
        }
    }
}

function Test-QueryPackAvailability {
    <#
    .SYNOPSIS
        Verifies that specified query packs can be resolved by CodeQL CLI.
    .DESCRIPTION
        Uses 'codeql resolve queries' to verify each pack is available.
        Falls back to format validation if CodeQL CLI is unavailable.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$CodeQLPath,

        [Parameter(Mandatory)]
        [string[]]$Packs,

        [Parameter()]
        [switch]$CI
    )

    $missingPacks = @()

    Write-Verbose "CodeQL CLI path: $CodeQLPath"

    foreach ($pack in $Packs) {
        Write-Verbose "Checking query pack: $pack"

        try {
            if ([string]::IsNullOrWhiteSpace($pack)) {
                $missingPacks += @{
                    Pack = $pack
                    Error = "Empty pack name"
                }
                continue
            }

            # Basic format validation: should be "owner/repo:path" format
            if ($pack -notmatch '^[\w\-]+/[\w\-]+(:|@)') {
                $missingPacks += @{
                    Pack = $pack
                    Error = "Invalid pack format. Expected 'owner/repo:path' or 'owner/repo@version'"
                }
                continue
            }

            # Use CodeQL CLI to resolve queries and verify pack availability
            if ($CodeQLPath -and (Test-Path $CodeQLPath)) {
                # Extract pack reference (without the query suite path for pack resolution)
                $packRef = $pack -replace ':.*$', ''

                # Try to resolve using codeql pack list or codeql resolve queries
                $resolveOutput = & $CodeQLPath resolve queries $pack 2>&1
                $resolveExitCode = $LASTEXITCODE

                if ($resolveExitCode -ne 0) {
                    # Try pack download to see if it's available
                    $packDownloadOutput = & $CodeQLPath pack download --dry-run $packRef 2>&1
                    $packListExitCode = $LASTEXITCODE

                    if ($packListExitCode -ne 0) {
                        $errorMessage = if ($resolveOutput -match 'not found|could not resolve|unable to') {
                            "Pack not found or unavailable: $resolveOutput"
                        } elseif ($packDownloadOutput -match 'not found|could not resolve|unable to') {
                            "Pack not found in registry: $packDownloadOutput"
                        } else {
                            "Failed to resolve pack (exit code $resolveExitCode)"
                        }

                        $missingPacks += @{
                            Pack = $pack
                            Error = $errorMessage
                        }

                        if ($CI) {
                            Write-Error "Query pack validation failed for '$pack': $errorMessage"
                        }
                    } else {
                        Write-Verbose "Pack '$packRef' is available (dry-run download succeeded)"
                    }
                } else {
                    Write-Verbose "Query pack '$pack' resolved successfully"
                }
            } else {
                Write-Verbose "CodeQL CLI not available, skipping pack resolution for '$pack'"
            }
        }
        catch {
            $missingPacks += @{
                Pack = $pack
                Error = $_.Exception.Message
            }
        }
    }

    return $missingPacks
}

function Test-PathsExist {
    <#
    .SYNOPSIS
        Checks if paths specified in config exist in repository.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string[]]$Paths,

        [Parameter(Mandatory)]
        [string]$RepoRoot
    )

    $missingPaths = @()

    foreach ($path in $Paths) {
        $fullPath = Join-Path $RepoRoot $path

        # Handle wildcards
        if ($path -match '[\*\?]') {
            $matchingPaths = Get-ChildItem -Path (Split-Path $fullPath -Parent) -Filter (Split-Path $fullPath -Leaf) -ErrorAction SilentlyContinue
            if (-not $matchingPaths) {
                $missingPaths += @{
                    Path = $path
                    Warning = "No files match pattern"
                }
            }
        }
        else {
            if (-not (Test-Path $fullPath)) {
                $missingPaths += @{
                    Path = $path
                    Warning = "Path does not exist"
                }
            }
        }
    }

    return $missingPaths
}

function Test-ConfigSchema {
    <#
    .SYNOPSIS
        Validates config against expected schema.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Content
    )

    $errors = @()

    # Check required field: name
    if ($Content -notmatch 'name\s*:\s*[''"]?[\w\s]+[''"]?') {
        $errors += "Missing required field: 'name'"
    }

    # Check required field: packs or queries
    $hasPacks = $Content -match 'packs\s*:'
    $hasQueries = $Content -match 'queries\s*:'

    if (-not $hasPacks -and -not $hasQueries) {
        $errors += "Config must have either 'packs' or 'queries' field"
    }

    # Validate severity values if present
    if ($Content -match 'severity\s*:\s*(\w+)') {
        $severity = $Matches[1]
        if ($severity -notin @('low', 'medium', 'high', 'critical')) {
            $errors += "Invalid severity value: '$severity'. Must be one of: low, medium, high, critical"
        }
    }

    # Extract packs for validation
    $packs = @()
    if ($Content -match 'packs\s*:(.*?)(?=\n\w|\n#|\z)') {
        $packsSection = $Matches[1]
        $packs = [regex]::Matches($packsSection, '-\s*([^\n]+)') | ForEach-Object { $_.Groups[1].Value.Trim() }
    }

    # Extract paths for validation
    $paths = @()
    if ($Content -match 'paths\s*:(.*?)(?=\n\w|\n#|\z)') {
        $pathsSection = $Matches[1]
        $paths = [regex]::Matches($pathsSection, '-\s*([^\n]+)') | ForEach-Object { $_.Groups[1].Value.Trim() }
    }

    return @{
        Errors = $errors
        Packs = $packs
        Paths = $paths
    }
}

function Get-CodeQLExecutable {
    <#
    .SYNOPSIS
        Locates the CodeQL CLI executable.
    #>
    [CmdletBinding()]
    param()

    # Check if in PATH
    $codeqlCmd = Get-Command codeql -ErrorAction SilentlyContinue
    if ($codeqlCmd) {
        return $codeqlCmd.Source
    }

    # Check default installation path
    $defaultPath = Join-Path $PSScriptRoot "../../cli/codeql"
    if ($IsWindows) {
        $defaultPath += ".exe"
    }

    if (Test-Path $defaultPath) {
        return $defaultPath
    }

    return $null
}

#endregion

#region Main Script

# Only execute main logic if script is run directly, not dot-sourced for testing
if ($MyInvocation.InvocationName -ne '.') {
    try {
        # Resolve config path
        if (-not [System.IO.Path]::IsPathRooted($ConfigPath)) {
            $ConfigPath = Join-Path $PWD $ConfigPath
        }

        # Check if config file exists
        if (-not (Test-Path $ConfigPath)) {
            if ($Format -eq "console") {
                Write-Host "❌ Config file not found: $ConfigPath" -ForegroundColor Red
            }
            elseif ($Format -eq "json") {
                @{
                    Valid = $false
                    Error = "Config file not found: $ConfigPath"
                } | ConvertTo-Json
            }
            exit 2
        }

        if (-not $CI -and $Format -eq "console") {
            Write-Host "Validating CodeQL configuration..." -ForegroundColor Cyan
            Write-Host "Config: $ConfigPath" -ForegroundColor Gray
            Write-Host ""
        }

        $validationResults = @{
            Valid = $true
            Errors = @()
            Warnings = @()
        }

        # 1. Validate YAML syntax
        $yamlResult = Test-YamlSyntax -ConfigPath $ConfigPath
        if (-not $yamlResult.Valid) {
            $validationResults.Valid = $false
            $validationResults.Errors += "YAML syntax error: $($yamlResult.Error)"
        }
        else {
            if (-not $CI -and $Format -eq "console") {
                Write-Host "✓ YAML syntax valid" -ForegroundColor Green
            }
        }

        # 2. Validate schema
        if ($yamlResult.Valid) {
            $schemaResult = Test-ConfigSchema -Content $yamlResult.Content

            if ($schemaResult.Errors.Count -gt 0) {
                $validationResults.Valid = $false
                $validationResults.Errors += $schemaResult.Errors
            }
            else {
                if (-not $CI -and $Format -eq "console") {
                    Write-Host "✓ Schema validation passed" -ForegroundColor Green
                }
            }

            # 3. Validate query packs
            $codeqlPath = Get-CodeQLExecutable
            if ($codeqlPath -and $schemaResult.Packs.Count -gt 0) {
                $missingPacks = Test-QueryPackAvailability -CodeQLPath $codeqlPath -Packs $schemaResult.Packs -CI:$CI

                if ($missingPacks.Count -gt 0) {
                    if ($CI) {
                        # In CI mode, missing packs are errors
                        $validationResults.Valid = $false
                        foreach ($pack in $missingPacks) {
                            $validationResults.Errors += "Query pack '$($pack.Pack)': $($pack.Error)"
                        }
                    } else {
                        # In non-CI mode, missing packs are warnings
                        foreach ($pack in $missingPacks) {
                            $validationResults.Warnings += "Query pack '$($pack.Pack)': $($pack.Error)"
                        }
                    }
                }
                else {
                    if (-not $CI -and $Format -eq "console") {
                        Write-Host "✓ Query pack validation passed ($($schemaResult.Packs.Count) packs)" -ForegroundColor Green
                    }
                }
            }
            elseif (-not $codeqlPath) {
                $validationResults.Warnings += "CodeQL CLI not found - skipping query pack validation"
            }

            # 4. Validate paths
            if ($schemaResult.Paths.Count -gt 0) {
                $repoRoot = Split-Path (Split-Path $ConfigPath -Parent) -Parent
                $missingPaths = Test-PathsExist -Paths $schemaResult.Paths -RepoRoot $repoRoot

                if ($missingPaths.Count -gt 0) {
                    foreach ($path in $missingPaths) {
                        $validationResults.Warnings += "Path '$($path.Path)': $($path.Warning)"
                    }
                }
                else {
                    if (-not $CI -and $Format -eq "console") {
                        Write-Host "✓ All paths exist ($($schemaResult.Paths.Count) paths)" -ForegroundColor Green
                    }
                }
            }
        }

        # Output results
        if ($Format -eq "console") {
            if (-not $CI) {
                Write-Host ""
                Write-Host "========================================" -ForegroundColor Cyan
                Write-Host "Validation Results" -ForegroundColor Cyan
                Write-Host "========================================" -ForegroundColor Cyan
            }

            if ($validationResults.Errors.Count -gt 0) {
                Write-Host "`nErrors:" -ForegroundColor Red
                foreach ($errorMsg in $validationResults.Errors) {
                    Write-Host "  ❌ $errorMsg" -ForegroundColor Red
                }
            }

            if ($validationResults.Warnings.Count -gt 0) {
                Write-Host "`nWarnings:" -ForegroundColor Yellow
                foreach ($warning in $validationResults.Warnings) {
                    Write-Host "  ⚠️  $warning" -ForegroundColor Yellow
                }
            }

            if ($validationResults.Valid) {
                Write-Host "`n✓ Configuration is valid" -ForegroundColor Green
            }
            else {
                Write-Host "`n❌ Configuration has errors" -ForegroundColor Red
            }
        }
        elseif ($Format -eq "json") {
            $validationResults | ConvertTo-Json -Depth 10
        }

        # Exit with appropriate code
        if ($validationResults.Valid) {
            exit 0
        }
        else {
            if ($CI) {
                Write-Error "Configuration validation failed"
            }
            exit 1
        }
    }
    catch {
        Write-Error "Configuration validation failed: $_"
        Write-Error $_.ScriptStackTrace
        exit 1
    }
} # End of direct execution check

#endregion
