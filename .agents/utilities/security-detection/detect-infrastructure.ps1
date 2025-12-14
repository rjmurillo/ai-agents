<#
.SYNOPSIS
    Detects infrastructure and security-critical file changes.

.DESCRIPTION
    Analyzes changed files to identify those requiring security agent review.
    Returns risk level and matching patterns.

.PARAMETER ChangedFiles
    Array of changed file paths to analyze.

.PARAMETER UseGitStaged
    If specified, analyzes staged files from git.

.EXAMPLE
    .\detect-infrastructure.ps1 -UseGitStaged

.EXAMPLE
    .\detect-infrastructure.ps1 -ChangedFiles @(".github/workflows/ci.yml", "src/auth/login.cs")
#>

param(
    [Parameter(Mandatory = $false)]
    [string[]]$ChangedFiles,

    [Parameter(Mandatory = $false)]
    [switch]$UseGitStaged
)

# Critical patterns - security review REQUIRED
$CriticalPatterns = @(
    "^\.github/workflows/.*\.(yml|yaml)$",
    "^\.github/actions/",
    "^\.githooks/",
    "^\.husky/",
    ".*/Auth/",
    ".*/Authentication/",
    ".*/Authorization/",
    ".*/Security/",
    ".*/Identity/",
    ".*Auth.*\.(cs|ts|js|py)$",
    "\.env.*$",
    ".*\.(pem|key|p12|pfx|jks)$",
    ".*secret.*",
    ".*credential.*",
    ".*password.*"
)

# High patterns - security review RECOMMENDED
$HighPatterns = @(
    "^build/.*\.(ps1|sh|cmd|bat)$",
    "^scripts/.*\.(ps1|sh)$",
    "^Makefile$",
    "^Dockerfile.*$",
    "^docker-compose.*\.(yml|yaml)$",
    ".*/Controllers/",
    ".*/Endpoints/",
    ".*/Handlers/",
    ".*/Middleware/",
    "^appsettings.*\.json$",
    "^web\.config$",
    "^app\.config$",
    "^config/.*\.(json|yml|yaml)$",
    ".*\.tf$",
    ".*\.tfvars$",
    ".*\.bicep$",
    "^nuget\.config$",
    "^\.npmrc$"
)

function Test-Pattern {
    param(
        [string]$FilePath,
        [string[]]$Patterns
    )

    foreach ($pattern in $Patterns) {
        if ($FilePath -match $pattern) {
            return $true
        }
    }
    return $false
}

function Get-SecurityRiskLevel {
    param(
        [string]$FilePath
    )

    # Normalize path separators
    $normalizedPath = $FilePath -replace '\\', '/'

    if (Test-Pattern -FilePath $normalizedPath -Patterns $CriticalPatterns) {
        return "critical"
    }
    elseif (Test-Pattern -FilePath $normalizedPath -Patterns $HighPatterns) {
        return "high"
    }
    else {
        return "none"
    }
}

# Get files to analyze
if ($UseGitStaged) {
    $ChangedFiles = git diff --cached --name-only 2>$null
    if (-not $ChangedFiles) {
        $ChangedFiles = @()
    }
}

if (-not $ChangedFiles -or $ChangedFiles.Count -eq 0) {
    Write-Host "No files to analyze." -ForegroundColor Gray
    exit 0
}

# Analyze files
$findings = @()
$highestRisk = "none"

foreach ($file in $ChangedFiles) {
    $risk = Get-SecurityRiskLevel -FilePath $file

    if ($risk -ne "none") {
        $findings += [PSCustomObject]@{
            File      = $file
            RiskLevel = $risk
        }

        if ($risk -eq "critical") {
            $highestRisk = "critical"
        }
        elseif ($risk -eq "high" -and $highestRisk -ne "critical") {
            $highestRisk = "high"
        }
    }
}

# Output results
if ($findings.Count -gt 0) {
    Write-Host ""
    Write-Host "=== Security Review Detection ===" -ForegroundColor Yellow
    Write-Host ""

    if ($highestRisk -eq "critical") {
        Write-Host "CRITICAL: Security agent review REQUIRED" -ForegroundColor Red
    }
    else {
        Write-Host "HIGH: Security agent review RECOMMENDED" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "Matching files:" -ForegroundColor Cyan

    foreach ($finding in $findings) {
        $color = if ($finding.RiskLevel -eq "critical") { "Red" } else { "Yellow" }
        Write-Host "  [$($finding.RiskLevel.ToUpper())] $($finding.File)" -ForegroundColor $color
    }

    Write-Host ""
    Write-Host "Run security agent before implementation:" -ForegroundColor Gray
    Write-Host '  Task(subagent_type="security", prompt="Review infrastructure changes")' -ForegroundColor Gray
    Write-Host ""

    # Return non-zero for CI detection (but 0 for pre-commit non-blocking)
    exit 0
}
else {
    Write-Host "No infrastructure/security files detected." -ForegroundColor Green
    exit 0
}
