<#
.SYNOPSIS
    Validates skill files follow the atomic format (one skill per file).

.DESCRIPTION
    Enforces ADR-017 skill format requirements:
    - One skill per file (no bundled skills)
    - Files with `## Skill-` headers are flagged as bundled format

    This validation runs on staged .serena/memories/ files during pre-commit.

.PARAMETER Path
    Path to the memories directory. Defaults to .serena/memories/.

.PARAMETER CI
    Run in CI mode (stricter output, exit codes).

.PARAMETER StagedOnly
    Only check staged files (for pre-commit hook).

.EXAMPLE
    pwsh scripts/Validate-SkillFormat.ps1

.EXAMPLE
    pwsh scripts/Validate-SkillFormat.ps1 -StagedOnly

.NOTES
    Related: ADR-017, Issue #307
#>
[CmdletBinding()]
param(
    [string]$Path = ".serena/memories",
    [switch]$CI,
    [switch]$StagedOnly
)

$ErrorActionPreference = 'Stop'
$script:ExitCode = 0
$script:BundledFiles = @()

# Get files to check
if ($StagedOnly) {
    # Get staged memory files from git
    $stagedFiles = git diff --cached --name-only --diff-filter=ACMR 2>$null |
        Where-Object { $_ -match '^\.serena/memories/.*\.md$' -and $_ -notmatch 'skills-.*-index\.md$' }

    if (-not $stagedFiles) {
        Write-Host "No skill files staged. Skipping format validation." -ForegroundColor Gray
        exit 0
    }

    $filesToCheck = $stagedFiles | ForEach-Object { Get-Item $_ -ErrorAction SilentlyContinue }
} else {
    # Check all skill files (exclude index files)
    $filesToCheck = Get-ChildItem -Path $Path -Filter "*.md" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch '^skills-.*-index\.md$' -and $_.Name -ne 'memory-index.md' }
}

if (-not $filesToCheck) {
    Write-Host "No skill files found to validate." -ForegroundColor Gray
    exit 0
}

Write-Host "Validating skill format (ADR-017: one skill per file)..." -ForegroundColor Cyan

foreach ($file in $filesToCheck) {
    $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
    if (-not $content) { continue }

    # Count skill headers (## Skill-*-NNN:)
    $skillHeaders = [regex]::Matches($content, '(?m)^## Skill-[A-Za-z]+-[0-9]+:')

    if ($skillHeaders.Count -gt 1) {
        # Bundled format detected
        Write-Host "  BUNDLED: $($file.Name) contains $($skillHeaders.Count) skills" -ForegroundColor Yellow
        $script:BundledFiles += @{
            File = $file.Name
            Count = $skillHeaders.Count
        }
        $script:ExitCode = 1
    }
}

# Summary
Write-Host ""
if ($script:BundledFiles.Count -gt 0) {
    Write-Host "=== Bundled Format Detected ===" -ForegroundColor Yellow
    Write-Host "The following files contain multiple skills:" -ForegroundColor Yellow
    $script:BundledFiles | ForEach-Object {
        Write-Host "  - $($_.File): $($_.Count) skills" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "ADR-017 requires ONE skill per file. No exceptions." -ForegroundColor Red
    Write-Host "Split bundled skills into separate atomic files." -ForegroundColor Red
    Write-Host ""

    if ($CI) {
        Write-Host "Result: FAILED" -ForegroundColor Red
        exit 1
    } else {
        Write-Host "Result: WARNING (non-blocking for legacy files)" -ForegroundColor Yellow
        exit 0
    }
} else {
    Write-Host "Result: PASSED - All skill files are atomic format" -ForegroundColor Green
    exit 0
}
