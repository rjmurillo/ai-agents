<#
.SYNOPSIS
    Validates PR readiness by checking size, scope, and quality gates.

.DESCRIPTION
    Runs pre-PR creation checks to ensure the branch is ready for review.
    Validates commit count, changed file count, total additions, critique
    verdicts, and ADR compliance.

    Checks:
    1. Commit count (max 20)
    2. Changed files count (max 10)
    3. Total additions (max 500 lines)
    4. Synthesis panel verdict (no blocking critiques)
    5. ADR compliance (basic structure check)

    Exit codes:
      0 = PASS (all checks passed)
      1 = FAIL (one or more checks failed)
      2 = ERROR (environment or configuration issue)

    See: ADR-035 Exit Code Standardization

.PARAMETER BaseBranch
    The base branch to compare against. Default: origin/main.

.PARAMETER MaxCommits
    Maximum allowed commits. Default: 20.

.PARAMETER MaxFiles
    Maximum allowed changed files. Default: 10.

.PARAMETER MaxAdditions
    Maximum allowed line additions. Default: 500.

.PARAMETER CritiquePath
    Path to critique directory. Default: .agents/critique/ relative to repo root.

.EXAMPLE
    .\Validate-PRReadiness.ps1
    # Run all checks against origin/main

.EXAMPLE
    .\Validate-PRReadiness.ps1 -BaseBranch origin/develop
    # Run checks against a different base branch

.EXAMPLE
    .\Validate-PRReadiness.ps1 -MaxCommits 30 -MaxFiles 15
    # Run with custom thresholds

.NOTES
    Author: AI Agents DevOps
    Related: Issue #934 (Create pre-PR validation script)
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$BaseBranch = "origin/main",

    [Parameter()]
    [int]$MaxCommits = 20,

    [Parameter()]
    [int]$MaxFiles = 10,

    [Parameter()]
    [int]$MaxAdditions = 500,

    [Parameter()]
    [string]$CritiquePath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

#region Color Output

$NoColor = $env:NO_COLOR -or $env:TERM -eq 'dumb' -or $env:CI

if ($NoColor) {
    $ColorReset = ""
    $ColorRed = ""
    $ColorYellow = ""
    $ColorGreen = ""
    $ColorCyan = ""
    $ColorMagenta = ""
} else {
    $ColorReset = "`e[0m"
    $ColorRed = "`e[31m"
    $ColorYellow = "`e[33m"
    $ColorGreen = "`e[32m"
    $ColorCyan = "`e[36m"
    $ColorMagenta = "`e[35m"
}

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = $ColorReset
    )
    if ($NoColor) {
        Write-Host $Message
    } else {
        Write-Host "$Color$Message$ColorReset"
    }
}

function Write-Status {
    param(
        [ValidateSet('PASS', 'FAIL', 'WARNING', 'SKIP', 'RUNNING')]
        [string]$Status,
        [string]$Message
    )

    $color = switch ($Status) {
        'PASS' { $ColorGreen }
        'FAIL' { $ColorRed }
        'WARNING' { $ColorYellow }
        'SKIP' { $ColorCyan }
        'RUNNING' { $ColorCyan }
        default { $ColorReset }
    }

    Write-ColorOutput "[$Status] $Message" $color
}

#endregion

#region Environment Validation

$RepoRoot = git rev-parse --show-toplevel 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Status 'FAIL' "Not inside a git repository"
    exit 2
}

if ([string]::IsNullOrWhiteSpace($CritiquePath)) {
    $CritiquePath = Join-Path $RepoRoot ".agents" "critique"
}

# Verify the base branch ref exists
$null = git rev-parse --verify $BaseBranch 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Status 'FAIL' "Base branch '$BaseBranch' not found. Run 'git fetch origin' first."
    exit 2
}

#endregion

#region Validation State

$CheckResults = @()
$StartTime = Get-Date

#endregion

#region Helper Functions

function Add-CheckResult {
    param(
        [string]$Name,
        [bool]$Passed,
        [string]$Detail
    )
    $script:CheckResults += [PSCustomObject]@{
        Name = $Name
        Status = if ($Passed) { 'PASS' } else { 'FAIL' }
        Detail = $Detail
    }
}

function Get-CommitCount {
    param([string]$Base)
    $output = git rev-list --count "HEAD" "^$Base" 2>&1
    if ($LASTEXITCODE -ne 0) {
        return -1
    }
    return [int]$output
}

function Get-ChangedFileCount {
    param([string]$Base)
    $files = git diff --name-only $Base 2>&1
    if ($LASTEXITCODE -ne 0) {
        return -1
    }
    if ([string]::IsNullOrWhiteSpace($files)) {
        return 0
    }
    $fileList = @($files -split "`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    return $fileList.Count
}

function Get-TotalAddition {
    param([string]$Base)
    $statOutput = git diff --stat $Base 2>&1
    if ($LASTEXITCODE -ne 0) {
        return -1
    }
    # The last line of git diff --stat looks like:
    #  N files changed, M insertions(+), D deletions(-)
    # or just: N files changed, M insertions(+)
    $lines = @($statOutput -split "`n")
    $summaryLine = $lines[-1]
    if ($summaryLine -match '(\d+)\s+insertion') {
        return [int]$Matches[1]
    }
    return 0
}

function Test-SynthesisPanelVerdict {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return @{ Passed = $true; Detail = "No critique directory found (check skipped)" }
    }

    $critiqueFiles = Get-ChildItem -Path $Path -Filter "*.md" -File -ErrorAction SilentlyContinue
    if (-not $critiqueFiles -or $critiqueFiles.Count -eq 0) {
        return @{ Passed = $true; Detail = "No critique files found (check skipped)" }
    }

    $blockingFiles = @()

    foreach ($file in $critiqueFiles) {
        $content = Get-Content -Path $file.FullName -Raw -ErrorAction SilentlyContinue
        if ([string]::IsNullOrWhiteSpace($content)) {
            continue
        }

        # Check for blocking verdicts: REJECTED or NEEDS_CHANGES in the Verdict section
        $hasBlockingVerdict = $false
        if ($content -match '(?m)^##\s+(?:Final\s+)?Verdict\s*\r?\n\s*\r?\n\*\*\s*(?:REJECTED|NEEDS_CHANGES)') {
            $hasBlockingVerdict = $true
        }
        if ($content -match '(?m)REJECTED\s*-\s*Critical') {
            $hasBlockingVerdict = $true
        }

        # Also check for P0/P1 critical issues that are unchecked (blocking)
        $hasBlockingPriority = $false
        if ($content -match '(?m)^-\s+\[\s\]\s+.*(?:Critical|CRITICAL|P0|P1)') {
            $hasBlockingPriority = $true
        }

        if ($hasBlockingVerdict -and $hasBlockingPriority) {
            $blockingFiles += $file.Name
        }
    }

    if ($blockingFiles.Count -gt 0) {
        $fileList = $blockingFiles -join ", "
        return @{
            Passed = $false
            Detail = "Blocking critique(s) found: $fileList"
        }
    }

    return @{ Passed = $true; Detail = "No blocking critiques ($($critiqueFiles.Count) file(s) checked)" }
}

function Test-ADRCompliance {
    $adrPath = Join-Path $RepoRoot ".agents" "architecture"
    if (-not (Test-Path $adrPath)) {
        return @{ Passed = $true; Detail = "No architecture directory found (check skipped)" }
    }

    $adrFiles = Get-ChildItem -Path $adrPath -Filter "ADR-*.md" -File -ErrorAction SilentlyContinue
    if (-not $adrFiles -or $adrFiles.Count -eq 0) {
        return @{ Passed = $true; Detail = "No ADR files found (check skipped)" }
    }

    $issueFiles = @()
    foreach ($file in $adrFiles) {
        $content = Get-Content -Path $file.FullName -Raw -ErrorAction SilentlyContinue
        if ([string]::IsNullOrWhiteSpace($content)) {
            continue
        }
        # Basic structure check: ADR should have Status and Decision sections
        $hasStatus = $content -match '(?m)^##\s+Status'
        $hasDecision = $content -match '(?m)^##\s+Decision'
        if (-not $hasStatus -or -not $hasDecision) {
            $issueFiles += $file.Name
        }
    }

    if ($issueFiles.Count -gt 0) {
        $fileList = $issueFiles -join ", "
        return @{
            Passed = $false
            Detail = "ADR(s) missing required sections (Status, Decision): $fileList"
        }
    }

    return @{ Passed = $true; Detail = "All $($adrFiles.Count) ADR(s) have required structure" }
}

#endregion

#region Header

Write-Host ""
Write-ColorOutput "=== PR Readiness Validation ===" $ColorMagenta
Write-Host "Repository: $RepoRoot"
Write-Host "Base branch: $BaseBranch"
Write-Host "Thresholds: commits=$MaxCommits, files=$MaxFiles, additions=$MaxAdditions"
Write-Host "Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host ""

#endregion

#region Check 1: Commit Count

Write-Status 'RUNNING' "Checking commit count..."

$commitCount = Get-CommitCount -Base $BaseBranch
if ($commitCount -lt 0) {
    Write-Status 'FAIL' "Failed to count commits"
    Add-CheckResult -Name "Commit Count" -Passed $false -Detail "git rev-list failed"
} elseif ($commitCount -gt $MaxCommits) {
    Write-Status 'FAIL' "Commit count: $commitCount (max $MaxCommits)"
    Write-ColorOutput "  Remediation: Squash commits with 'git rebase -i $BaseBranch'" $ColorYellow
    Write-ColorOutput "  Consider splitting into smaller PRs if changes are independent." $ColorYellow
    Add-CheckResult -Name "Commit Count" -Passed $false -Detail "$commitCount commits (max $MaxCommits)"
} else {
    Write-Status 'PASS' "Commit count: $commitCount (max $MaxCommits)"
    Add-CheckResult -Name "Commit Count" -Passed $true -Detail "$commitCount commits"
}

#endregion

#region Check 2: Changed Files Count

Write-Status 'RUNNING' "Checking changed files count..."

$fileCount = Get-ChangedFileCount -Base $BaseBranch
if ($fileCount -lt 0) {
    Write-Status 'FAIL' "Failed to count changed files"
    Add-CheckResult -Name "Changed Files" -Passed $false -Detail "git diff failed"
} elseif ($fileCount -gt $MaxFiles) {
    Write-Status 'FAIL' "Changed files: $fileCount (max $MaxFiles)"
    Write-ColorOutput "  Remediation: Split changes into multiple focused PRs." $ColorYellow
    Write-ColorOutput "  Group related changes together. Use 'git diff --name-only $BaseBranch' to review." $ColorYellow
    Add-CheckResult -Name "Changed Files" -Passed $false -Detail "$fileCount files (max $MaxFiles)"
} else {
    Write-Status 'PASS' "Changed files: $fileCount (max $MaxFiles)"
    Add-CheckResult -Name "Changed Files" -Passed $true -Detail "$fileCount files"
}

#endregion

#region Check 3: Total Additions

Write-Status 'RUNNING' "Checking total additions..."

$additions = Get-TotalAddition -Base $BaseBranch
if ($additions -lt 0) {
    Write-Status 'FAIL' "Failed to count additions"
    Add-CheckResult -Name "Total Additions" -Passed $false -Detail "git diff --stat failed"
} elseif ($additions -gt $MaxAdditions) {
    Write-Status 'FAIL' "Total additions: $additions (max $MaxAdditions)"
    Write-ColorOutput "  Remediation: Break the PR into smaller, incremental changes." $ColorYellow
    Write-ColorOutput "  Move generated or boilerplate code to separate PRs." $ColorYellow
    Add-CheckResult -Name "Total Additions" -Passed $false -Detail "$additions additions (max $MaxAdditions)"
} else {
    Write-Status 'PASS' "Total additions: $additions (max $MaxAdditions)"
    Add-CheckResult -Name "Total Additions" -Passed $true -Detail "$additions additions"
}

#endregion

#region Check 4: Synthesis Panel Verdict

Write-Status 'RUNNING' "Checking synthesis panel verdicts..."

$synthesisResult = Test-SynthesisPanelVerdict -Path $CritiquePath
if ($synthesisResult.Passed) {
    Write-Status 'PASS' "Synthesis panel: $($synthesisResult.Detail)"
} else {
    Write-Status 'FAIL' "Synthesis panel: $($synthesisResult.Detail)"
    Write-ColorOutput "  Remediation: Address blocking critique findings before creating PR." $ColorYellow
    Write-ColorOutput "  Review files in $CritiquePath for REJECTED or NEEDS_CHANGES verdicts." $ColorYellow
}
Add-CheckResult -Name "Synthesis Panel" -Passed $synthesisResult.Passed -Detail $synthesisResult.Detail

#endregion

#region Check 5: ADR Compliance

Write-Status 'RUNNING' "Checking ADR compliance..."

$adrResult = Test-ADRCompliance
if ($adrResult.Passed) {
    Write-Status 'PASS' "ADR compliance: $($adrResult.Detail)"
} else {
    Write-Status 'FAIL' "ADR compliance: $($adrResult.Detail)"
    Write-ColorOutput "  Remediation: Ensure each ADR has '## Status' and '## Decision' sections." $ColorYellow
    Write-ColorOutput "  See .agents/architecture/ for ADR format examples." $ColorYellow
}
Add-CheckResult -Name "ADR Compliance" -Passed $adrResult.Passed -Detail $adrResult.Detail

#endregion

#region Summary

$EndTime = Get-Date
$Duration = ($EndTime - $StartTime).TotalSeconds
$PassedCount = @($CheckResults | Where-Object { $_.Status -eq 'PASS' }).Count
$FailedCount = @($CheckResults | Where-Object { $_.Status -eq 'FAIL' }).Count

Write-Host ""
Write-ColorOutput "=== PR Readiness Summary ===" $ColorMagenta
Write-Host "Duration: $($Duration.ToString('F2'))s"
Write-Host "Total Checks: $($CheckResults.Count)"
Write-ColorOutput "Passed: $PassedCount" $ColorGreen
Write-ColorOutput "Failed: $FailedCount" $(if ($FailedCount -gt 0) { $ColorRed } else { $ColorGreen })
Write-Host ""

Write-ColorOutput "=== Detailed Results ===" $ColorCyan
Write-Host ""

foreach ($result in $CheckResults) {
    $color = if ($result.Status -eq 'PASS') { $ColorGreen } else { $ColorRed }
    Write-ColorOutput "[$($result.Status)] $($result.Name): $($result.Detail)" $color
}

Write-Host ""

if ($FailedCount -gt 0) {
    Write-ColorOutput "RESULT: $FailedCount check(s) failed. PR is NOT ready." $ColorRed
    Write-Host ""
    Write-Host "Fix the issues above, then re-run this script."
    Write-Host ""
    exit 1
} else {
    Write-ColorOutput "RESULT: All checks passed. PR is ready for creation." $ColorGreen
    Write-Host ""
    exit 0
}

#endregion
