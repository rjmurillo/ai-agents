<#
.SYNOPSIS
    Orchestrates CodeQL database creation and analysis for the repository.

.DESCRIPTION
    This script performs a complete CodeQL security scan by:
    1. Auto-detecting languages in the repository (Python, GitHub Actions)
    2. Creating CodeQL databases for each detected language
    3. Running security queries against the databases using shared configuration
    4. Generating SARIF output files for review and upload
    5. Formatting results for console, JSON, or SARIF output

    The script supports database caching to avoid redundant analysis and follows
    the repository's PowerShell-only convention (ADR-005) with standardized exit
    codes (ADR-035).

.PARAMETER RepoPath
    Path to the repository root directory. Defaults to current directory.

.PARAMETER ConfigPath
    Path to the CodeQL configuration YAML file.
    Defaults to ".github/codeql/codeql-config.yml".

.PARAMETER DatabasePath
    Path where CodeQL databases will be created or cached.
    Defaults to ".codeql/db".

.PARAMETER ResultsPath
    Path where SARIF result files will be saved.
    Defaults to ".codeql/results".

.PARAMETER Languages
    Array of languages to scan. If not specified, languages are auto-detected.
    Supported values: "python", "actions"

.PARAMETER UseCache
    If specified, reuses cached databases if they are still valid (no config changes,
    no git HEAD changes). Significantly speeds up repeated scans.

.PARAMETER CI
    Enables CI mode with non-interactive behavior. In CI mode, the script exits with
    code 1 if any high or critical severity findings are detected.

.PARAMETER Format
    Output format for scan results.
    Valid values: "console" (colored summary), "sarif" (copy SARIF files), "json" (structured JSON)
    Defaults to "console".

.PARAMETER QuickScan
    Enables quick scan mode with targeted query selection (5-10 critical CWEs only).
    Uses .github/codeql/codeql-config-quick.yml instead of the default configuration.
    Quick scans complete in 5-15 seconds (cached database) vs 30-60 seconds (full scan).
    Designed for PostToolUse hooks and interactive development with 30-second timeout.

.EXAMPLE
    .\Invoke-CodeQLScan.ps1
    Auto-detects languages and performs full scan with console output

.EXAMPLE
    .\Invoke-CodeQLScan.ps1 -Languages "python","actions" -UseCache
    Scans only Python and GitHub Actions, using cached databases if valid

.EXAMPLE
    .\Invoke-CodeQLScan.ps1 -CI -Format json
    Runs in CI mode with JSON output, exits with error if findings detected

.EXAMPLE
    .\Invoke-CodeQLScan.ps1 -DatabasePath ".codeql/custom-db" -ResultsPath ".codeql/custom-results"
    Uses custom paths for databases and results

.NOTES
    Exit Codes (per ADR-035):
        0 = Success (no findings or not in CI mode)
        1 = Logic error or findings detected in CI mode
        2 = Configuration error (missing config, invalid paths)
        3 = External dependency error (CodeQL CLI not found, analysis failed)

    Requirements:
        - CodeQL CLI must be installed and in PATH (or in .codeql/cli/)
        - Git repository (for cache invalidation)
        - Valid codeql-config.yml

    Performance:
        - Database creation: ~30-120 seconds per language (first run)
        - Analysis: ~10-60 seconds per language
        - Cache: ~5-10 seconds for cache validation (subsequent runs)

.LINK
    https://codeql.github.com/docs/codeql-cli/
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
    [string[]]$Languages,

    [Parameter()]
    [switch]$UseCache,

    [Parameter()]
    [switch]$CI,

    [Parameter()]
    [ValidateSet("console", "sarif", "json")]
    [string]$Format = "console",

    [Parameter()]
    [switch]$QuickScan
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

#region Helper Functions

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

    throw "CodeQL CLI not found. Please install using Install-CodeQL.ps1 or add to PATH."
}

function Get-RepositoryLanguage {
    <#
    .SYNOPSIS
        Auto-detects programming languages in the repository.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$RepoPath
    )

    $detectedLanguages = @()

    # Check for Python files
    $pyFiles = Get-ChildItem -Path $RepoPath -Filter "*.py" -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if ($pyFiles) {
        $detectedLanguages += "python"
        Write-Verbose "Detected Python files"
    }

    # Check for GitHub Actions workflows
    $workflowPath = Join-Path $RepoPath ".github/workflows"
    if (Test-Path $workflowPath) {
        $workflowFiles = Get-ChildItem -Path $workflowPath -Filter "*.yml" -ErrorAction SilentlyContinue
        if ($workflowFiles) {
            $detectedLanguages += "actions"
            Write-Verbose "Detected GitHub Actions workflows"
        }
    }

    if ($detectedLanguages.Count -eq 0) {
        Write-Warning "No supported languages detected in repository"
    }

    return $detectedLanguages
}

function Test-DatabaseCache {
    <#
    .SYNOPSIS
        Validates if cached database is still current.
    .DESCRIPTION
        Performs comprehensive cache validation using metadata file:
        - Checks database directory existence
        - Validates config file hash (no changes)
        - Validates scripts directory hash (no changes to .codeql/scripts/)
        - Validates .github/codeql/ directory hash (no changes to config directory)
        - Checks git HEAD (no new commits)
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$DatabasePath,

        [Parameter(Mandatory)]
        [string]$ConfigPath,

        [Parameter(Mandatory)]
        [string]$RepoPath
    )

    # Check if database exists
    if (-not (Test-Path $DatabasePath)) {
        Write-Verbose "Database cache not found"
        return $false
    }

    # Check for cache metadata file
    $metadataPath = Join-Path $DatabasePath ".cache-metadata.json"
    if (-not (Test-Path $metadataPath)) {
        Write-Verbose "Cache metadata not found (old cache format)"
        return $false
    }

    try {
        $metadata = Get-Content $metadataPath -Raw | ConvertFrom-Json
    }
    catch {
        Write-Verbose "Failed to parse cache metadata: $_"
        return $false
    }

    # Validate git HEAD
    try {
        Push-Location $RepoPath
        $currentHead = git rev-parse HEAD 2>&1
        if ($LASTEXITCODE -eq 0 -and $currentHead -ne $metadata.git_head) {
            Write-Verbose "Git HEAD changed: $($metadata.git_head) -> $currentHead"
            return $false
        }
    }
    catch {
        Write-Verbose "Unable to check git HEAD: $_"
    }
    finally {
        Pop-Location
    }

    # Validate config hash
    if (Test-Path $ConfigPath) {
        $configHash = (Get-FileHash -Path $ConfigPath -Algorithm SHA256).Hash
        if ($configHash -ne $metadata.config_hash) {
            Write-Verbose "Config file changed (hash mismatch)"
            return $false
        }
    }

    # Validate scripts directory hash
    $scriptsDir = Join-Path $RepoPath ".codeql/scripts"
    if (Test-Path $scriptsDir) {
        $scriptsHash = Get-DirectoryHash -Path $scriptsDir
        if ($scriptsHash -ne $metadata.scripts_hash) {
            Write-Verbose "CodeQL scripts directory changed (hash mismatch)"
            return $false
        }
    }

    # Validate config directory hash
    $configDir = Join-Path $RepoPath ".github/codeql"
    if (Test-Path $configDir) {
        $configDirHash = Get-DirectoryHash -Path $configDir
        if ($configDirHash -ne $metadata.config_dir_hash) {
            Write-Verbose "CodeQL config directory changed (hash mismatch)"
            return $false
        }
    }

    Write-Verbose "Cache valid: git HEAD unchanged, config unchanged, scripts unchanged"
    return $true
}

function Get-DirectoryHash {
    <#
    .SYNOPSIS
        Computes a hash of all files in a directory (recursive).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        return ""
    }

    $files = Get-ChildItem -Path $Path -File -Recurse | Sort-Object FullName
    $hashInput = ($files | ForEach-Object {
        "$($_.FullName):$((Get-FileHash -Path $_.FullName -Algorithm SHA256).Hash)"
    }) -join "`n"

    return (Get-FileHash -InputStream ([System.IO.MemoryStream]::new([System.Text.Encoding]::UTF8.GetBytes($hashInput))) -Algorithm SHA256).Hash
}

function Invoke-CodeQLDatabaseCreate {
    <#
    .SYNOPSIS
        Creates a CodeQL database for the specified language.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$CodeQLPath,

        [Parameter(Mandatory)]
        [string]$Language,

        [Parameter(Mandatory)]
        [string]$SourceRoot,

        [Parameter(Mandatory)]
        [string]$DatabasePath,

        [Parameter(Mandatory)]
        [string]$ConfigPath,

        [Parameter(Mandatory)]
        [string]$RepoPath
    )

    $langDbPath = Join-Path $DatabasePath $Language

    if (-not $CI) {
        Write-Host "Creating CodeQL database for $Language..." -ForegroundColor Cyan
    }

    # Remove existing database for this language
    if (Test-Path $langDbPath) {
        Remove-Item -Path $langDbPath -Recurse -Force
    }

    try {
        & $CodeQLPath database create $langDbPath `
            --language=$Language `
            --source-root=$SourceRoot `
            2>&1 | Out-String | Write-Verbose

        if ($LASTEXITCODE -ne 0) {
            throw "CodeQL database creation failed with exit code $LASTEXITCODE"
        }

        if (-not $CI) {
            Write-Host "✓ Database created for $Language" -ForegroundColor Green
        }

        # Write cache metadata after successful database creation
        Write-CacheMetadata -DatabasePath $DatabasePath -ConfigPath $ConfigPath -RepoPath $RepoPath
    }
    catch {
        Write-Error "Failed to create CodeQL database for ${Language}: $_"
        throw
    }
}

function Write-CacheMetadata {
    <#
    .SYNOPSIS
        Writes cache metadata file for database invalidation tracking.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$DatabasePath,

        [Parameter(Mandatory)]
        [string]$ConfigPath,

        [Parameter(Mandatory)]
        [string]$RepoPath
    )

    try {
        # Get git HEAD
        Push-Location $RepoPath
        $gitHead = git rev-parse HEAD 2>&1
        if ($LASTEXITCODE -ne 0) {
            $gitHead = "unknown"
        }
    }
    catch {
        $gitHead = "unknown"
    }
    finally {
        Pop-Location
    }

    # Compute config hash
    $configHash = if (Test-Path $ConfigPath) {
        (Get-FileHash -Path $ConfigPath -Algorithm SHA256).Hash
    } else {
        ""
    }

    # Compute scripts directory hash
    $scriptsDir = Join-Path $RepoPath ".codeql/scripts"
    $scriptsHash = Get-DirectoryHash -Path $scriptsDir

    # Compute config directory hash
    $configDir = Join-Path $RepoPath ".github/codeql"
    $configDirHash = Get-DirectoryHash -Path $configDir

    $metadata = @{
        created = (Get-Date).ToUniversalTime().ToString('o')
        git_head = $gitHead
        config_hash = $configHash
        scripts_hash = $scriptsHash
        config_dir_hash = $configDirHash
    }

    $metadataPath = Join-Path $DatabasePath ".cache-metadata.json"
    $metadata | ConvertTo-Json -Depth 10 | Set-Content -Path $metadataPath -Encoding UTF8

    Write-Verbose "Cache metadata written to $metadataPath"
}

function Invoke-CodeQLDatabaseAnalyze {
    <#
    .SYNOPSIS
        Runs CodeQL analysis against the database.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$CodeQLPath,

        [Parameter(Mandatory)]
        [string]$Language,

        [Parameter(Mandatory)]
        [string]$DatabasePath,

        [Parameter(Mandatory)]
        [string]$ResultsPath,

        [Parameter(Mandatory)]
        [string]$ConfigPath
    )

    $langDbPath = Join-Path $DatabasePath $Language
    $sarifOutput = Join-Path $ResultsPath "$Language.sarif"

    if (-not $CI) {
        Write-Host "Analyzing $Language code..." -ForegroundColor Cyan
    }

    # Ensure results directory exists
    if (-not (Test-Path $ResultsPath)) {
        New-Item -ItemType Directory -Path $ResultsPath -Force | Out-Null
    }

    try {
        $analyzeArgs = @(
            "database", "analyze",
            $langDbPath,
            "--format=sarif-latest",
            "--output=$sarifOutput",
            "--sarif-category=$Language"
        )

        # Add config if it exists
        if (Test-Path $ConfigPath) {
            $analyzeArgs += "--config=$ConfigPath"
        }

        & $CodeQLPath @analyzeArgs 2>&1 | Out-String | Write-Verbose

        if ($LASTEXITCODE -ne 0) {
            throw "CodeQL analysis failed with exit code $LASTEXITCODE"
        }

        # Parse SARIF for findings count
        $sarif = Get-Content $sarifOutput -Raw | ConvertFrom-Json
        $findings = $sarif.runs[0].results

        $result = @{
            Language = $Language
            FindingsCount = $findings.Count
            Findings = $findings
            SarifPath = $sarifOutput
        }

        if (-not $CI) {
            $findingsColor = if ($findings.Count -eq 0) { "Green" } else { "Yellow" }
            Write-Host "✓ Analysis complete: $($findings.Count) findings" -ForegroundColor $findingsColor
        }

        return $result
    }
    catch {
        Write-Error "Failed to analyze CodeQL database for ${Language}: $_"
        throw
    }
}

function Format-ScanResult {
    <#
    .SYNOPSIS
        Formats scan results for the specified output format.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [hashtable[]]$Results,

        [Parameter(Mandatory)]
        [ValidateSet("console", "sarif", "json")]
        [string]$Format
    )

    switch ($Format) {
        "console" {
            Write-Host "`n========================================" -ForegroundColor Cyan
            Write-Host "CodeQL Scan Results" -ForegroundColor Cyan
            Write-Host "========================================" -ForegroundColor Cyan

            $totalFindings = 0
            foreach ($result in $Results) {
                $totalFindings += $result.FindingsCount

                $color = if ($result.FindingsCount -eq 0) { "Green" } else { "Yellow" }
                Write-Host "`n$($result.Language):" -ForegroundColor White -NoNewline
                Write-Host " $($result.FindingsCount) findings" -ForegroundColor $color

                if ($result.FindingsCount -gt 0 -and $result.Findings) {
                    # Group by severity
                    $bySeverity = $result.Findings | Group-Object -Property { $_.level ?? "note" }
                    foreach ($group in $bySeverity) {
                        $severityColor = switch ($group.Name) {
                            "error" { "Red" }
                            "warning" { "Yellow" }
                            default { "Gray" }
                        }
                        Write-Host "  - $($group.Name): $($group.Count)" -ForegroundColor $severityColor
                    }
                }

                Write-Host "  SARIF: $($result.SarifPath)" -ForegroundColor Gray
            }

            Write-Host "`n========================================" -ForegroundColor Cyan
            $summaryColor = if ($totalFindings -eq 0) { "Green" } else { "Yellow" }
            Write-Host "Total Findings: $totalFindings" -ForegroundColor $summaryColor
            Write-Host "========================================" -ForegroundColor Cyan
        }

        "json" {
            $jsonResults = @{
                TotalFindings = ($Results | Measure-Object -Property FindingsCount -Sum).Sum
                Languages = $Results | ForEach-Object {
                    @{
                        Language = $_.Language
                        FindingsCount = $_.FindingsCount
                        SarifPath = $_.SarifPath
                    }
                }
            }

            $jsonResults | ConvertTo-Json -Depth 10
        }

        "sarif" {
            Write-Host "SARIF files available at:" -ForegroundColor Cyan
            foreach ($result in $Results) {
                Write-Host "  $($result.SarifPath)" -ForegroundColor White
            }
        }
    }
}

#endregion

#region Main Script

# Only execute main logic if script is run directly, not dot-sourced for testing
if ($MyInvocation.InvocationName -ne '.') {
    try {
        # Resolve paths to absolute
        $RepoPath = Resolve-Path $RepoPath | Select-Object -ExpandProperty Path

        # Use quick config if -QuickScan is specified
        if ($QuickScan -and $ConfigPath -eq ".github/codeql/codeql-config.yml") {
            $ConfigPath = ".github/codeql/codeql-config-quick.yml"
            if (-not $CI) {
                Write-Host "Quick scan mode enabled (targeted queries)" -ForegroundColor Yellow
            }
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

        # Validate inputs
        if (-not (Test-Path $RepoPath)) {
            Write-Error "Repository path not found: $RepoPath"
            exit 2
        }

        if (-not (Test-Path $ConfigPath)) {
            Write-Warning "Config file not found at $ConfigPath. Proceeding without custom configuration."
        }

        # Locate CodeQL CLI
        $codeQLPath = Get-CodeQLExecutable

        if (-not $CI) {
            Write-Host "CodeQL CLI: $codeQLPath" -ForegroundColor Cyan
            Write-Host "Repository: $RepoPath" -ForegroundColor Cyan
            Write-Host ""
        }

        # Auto-detect or validate languages
        if (-not $Languages) {
            $Languages = Get-RepositoryLanguage -RepoPath $RepoPath
            if ($Languages.Count -eq 0) {
                Write-Warning "No languages detected for scanning"
                exit 0
            }
        }

        if (-not $CI) {
            Write-Host "Languages to scan: $($Languages -join ', ')" -ForegroundColor Cyan
            Write-Host ""
        }

        # Check cache validity
        $useCachedDb = $false
        if ($UseCache) {
            $useCachedDb = Test-DatabaseCache -DatabasePath $DatabasePath -ConfigPath $ConfigPath -RepoPath $RepoPath
            if ($useCachedDb) {
                if (-not $CI) {
                    Write-Host "Using cached databases (validated)" -ForegroundColor Green
                }
            }
        }

        # Create databases if needed
        if (-not $useCachedDb) {
            foreach ($lang in $Languages) {
                Invoke-CodeQLDatabaseCreate -CodeQLPath $codeQLPath -Language $lang -SourceRoot $RepoPath -DatabasePath $DatabasePath -ConfigPath $ConfigPath -RepoPath $RepoPath
            }
        }

        # Run analysis
        $analysisResults = @()
        foreach ($lang in $Languages) {
            $result = Invoke-CodeQLDatabaseAnalyze -CodeQLPath $codeQLPath -Language $lang -DatabasePath $DatabasePath -ResultsPath $ResultsPath -ConfigPath $ConfigPath
            $analysisResults += $result
        }

        # Format and display results
        Format-ScanResult -Results $analysisResults -Format $Format

        # Exit with error in CI mode if findings detected
        if ($CI) {
            $totalFindings = ($analysisResults | Measure-Object -Property FindingsCount -Sum).Sum
            if ($totalFindings -gt 0) {
                Write-Error "CodeQL scan detected $totalFindings findings"
                exit 1
            }
        }

        exit 0
    }
    catch {
        Write-Error "CodeQL scan failed: $_"
        Write-Error $_.ScriptStackTrace
        exit 3
    }
} # End of direct execution check

#endregion
