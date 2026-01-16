<#
.SYNOPSIS
    CodeQL scan skill wrapper providing unified interface for security analysis operations.

.DESCRIPTION
    Wrapper script for CodeQL scanning operations that provides skill-specific functionality
    with standardized exit codes (ADR-035) and error handling. Supports full scans, quick
    scans with caching, and configuration validation.

.PARAMETER Operation
    Operation type to perform:
    - full: Complete repository scan without cache
    - quick: Scan with cached databases (faster iteration)
    - validate: Validate CodeQL configuration only

.PARAMETER Languages
    Array of languages to scan. If not provided, auto-detects from repository.
    Valid values: "python", "actions"

.PARAMETER CI
    Enable CI mode. When enabled, exits with code 1 if findings are detected.

.EXAMPLE
    .\Invoke-CodeQLScanSkill.ps1 -Operation full
    Run a full repository scan with auto-detected languages.

.EXAMPLE
    .\Invoke-CodeQLScanSkill.ps1 -Operation quick
    Run a quick scan using cached databases.

.EXAMPLE
    .\Invoke-CodeQLScanSkill.ps1 -Operation validate
    Validate CodeQL configuration only.

.EXAMPLE
    .\Invoke-CodeQLScanSkill.ps1 -Operation full -CI
    Run full scan in CI mode (exit 1 on findings).

.EXAMPLE
    .\Invoke-CodeQLScanSkill.ps1 -Operation full -Languages "python"
    Scan only Python code.

.NOTES
    Exit Codes (ADR-035):
    - 0: Success (no findings or findings ignored)
    - 1: Findings detected (CI mode only)
    - 2: Configuration invalid
    - 3: Scan execution failed (CLI not found, script error)

    Related Scripts:
    - .codeql/scripts/Install-CodeQL.ps1
    - .codeql/scripts/Invoke-CodeQLScan.ps1
    - .codeql/scripts/Test-CodeQLConfig.ps1
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("full", "quick", "validate")]
    [string]$Operation = "full",

    [Parameter(Mandatory = $false)]
    [ValidateSet("python", "actions")]
    [string[]]$Languages,

    [Parameter(Mandatory = $false)]
    [switch]$CI
)

$ErrorActionPreference = 'Stop'

# Helper function for colored output
function Write-ColorOutput {
    param(
        [string]$Message,
        [ValidateSet("Success", "Error", "Warning", "Info")]
        [string]$Type = "Info"
    )

    $color = switch ($Type) {
        "Success" { "Green" }
        "Error" { "Red" }
        "Warning" { "Yellow" }
        "Info" { "Cyan" }
    }

    $prefix = switch ($Type) {
        "Success" { "[✓]" }
        "Error" { "[✗]" }
        "Warning" { "[!]" }
        "Info" { "[i]" }
    }

    Write-Host "$prefix $Message" -ForegroundColor $color
}

# Get repository root
$repoRoot = git rev-parse --show-toplevel 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-ColorOutput "Not in a git repository" -Type Error
    exit 3
}

# Define script paths
$codeqlCliPath = Join-Path $repoRoot ".codeql" "cli" "codeql"
if ($IsWindows) {
    $codeqlCliPath += ".exe"
}
$installScript = Join-Path $repoRoot ".codeql" "scripts" "Install-CodeQL.ps1"
$scanScript = Join-Path $repoRoot ".codeql" "scripts" "Invoke-CodeQLScan.ps1"
$configScript = Join-Path $repoRoot ".codeql" "scripts" "Test-CodeQLConfig.ps1"

Write-Host "`n=== CodeQL Security Scan ===" -ForegroundColor Cyan
Write-Host "Operation: $Operation" -ForegroundColor White
Write-Host ""

# Operation: validate
if ($Operation -eq "validate") {
    Write-ColorOutput "Validating CodeQL configuration..." -Type Info

    if (-not (Test-Path $configScript)) {
        Write-ColorOutput "Configuration script not found: $configScript" -Type Error
        exit 3
    }

    try {
        & pwsh -NoProfile -File $configScript
        $exitCode = $LASTEXITCODE

        if ($exitCode -eq 0) {
            Write-ColorOutput "Configuration validation passed" -Type Success
            exit 0
        }
        else {
            Write-ColorOutput "Configuration validation failed" -Type Error
            exit 2
        }
    }
    catch {
        Write-ColorOutput "Configuration validation failed: $_" -Type Error
        exit 2
    }
}

# Check if CodeQL CLI is installed (required for full and quick operations)
if (-not (Test-Path $codeqlCliPath)) {
    Write-ColorOutput "CodeQL CLI not found at: $codeqlCliPath" -Type Error
    Write-Host ""
    Write-ColorOutput "Install CodeQL CLI with:" -Type Info
    Write-Host "  pwsh $installScript -AddToPath" -ForegroundColor White
    Write-Host ""
    Write-ColorOutput "Or use VSCode task: 'CodeQL: Install CLI'" -Type Info
    exit 3
}

Write-ColorOutput "CodeQL CLI found at: $codeqlCliPath" -Type Success

# Check if scan script exists
if (-not (Test-Path $scanScript)) {
    Write-ColorOutput "Scan script not found: $scanScript" -Type Error
    exit 3
}

# Build scan arguments
$scanArgs = @(
    "-NoProfile"
    "-File"
    $scanScript
)

# Operation-specific arguments
switch ($Operation) {
    "full" {
        # Full scan - no cache
        Write-ColorOutput "Running full scan (rebuilding databases)..." -Type Info
    }
    "quick" {
        # Quick scan - use cache
        $scanArgs += "-UseCache"
        Write-ColorOutput "Running quick scan (using cached databases)..." -Type Info
    }
}

# Add language filter if specified
if ($Languages) {
    $scanArgs += "-Languages"
    $scanArgs += $Languages
    Write-ColorOutput "Scanning languages: $($Languages -join ', ')" -Type Info
}

# Add CI mode if specified
if ($CI) {
    $scanArgs += "-CI"
    Write-ColorOutput "CI mode enabled (exit 1 on findings)" -Type Info
}

Write-Host ""

# Execute scan
try {
    & pwsh @scanArgs
    $exitCode = $LASTEXITCODE

    Write-Host ""

    # Interpret exit code
    switch ($exitCode) {
        0 {
            Write-ColorOutput "Scan completed successfully" -Type Success
            if (Test-Path (Join-Path $repoRoot ".codeql" "results")) {
                Write-ColorOutput "SARIF results: .codeql/results/" -Type Info
            }
        }
        1 {
            # Findings detected in CI mode
            Write-ColorOutput "Scan completed with findings" -Type Warning
            Write-ColorOutput "Review SARIF files in .codeql/results/" -Type Info
        }
        2 {
            Write-ColorOutput "Configuration error" -Type Error
        }
        3 {
            Write-ColorOutput "Scan execution failed" -Type Error
        }
        default {
            Write-ColorOutput "Scan exited with unexpected code: $exitCode" -Type Warning
        }
    }

    exit $exitCode
}
catch {
    Write-ColorOutput "Scan failed: $_" -Type Error
    exit 3
}
