<#
.SYNOPSIS
    Unified shift-left validation runner for pre-PR checks.

.DESCRIPTION
    Runs all local validations before creating a pull request.
    Executes validations in optimized order (fast checks first).

    Validation sequence:
    1. Session End (for latest session log)
    2. Pester Tests (all unit tests)
    3. Markdown Lint (auto-fix and validate)
    4. Path Normalization (check for absolute paths) [skip if -Quick]
    5. Planning Artifacts (validate planning consistency) [skip if -Quick]
    6. Agent Drift (detect semantic drift) [skip if -Quick]

    Exit codes:
      0 = PASS (all validations succeeded)
      1 = FAIL (one or more validations failed)
      2 = ERROR (environment or configuration issue)

.PARAMETER Quick
    Skip slow validations (path normalization, planning artifacts, agent drift).
    Use for rapid iteration during development.

.PARAMETER SkipTests
    Skip Pester unit tests (use sparingly).

.EXAMPLE
    .\Validate-PrePR.ps1
    # Run all validations

.EXAMPLE
    .\Validate-PrePR.ps1 -Quick
    # Run fast validations only (session end, tests, markdown)

.EXAMPLE
    .\Validate-PrePR.ps1 -Verbose
    # Run with detailed output (use built-in -Verbose parameter)

.NOTES
    Author: AI Agents DevOps
    Related: Issue #325 (Unified shift-left validation runner)
    See: .agents/SHIFT-LEFT.md for workflow documentation
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Quick,

    [Parameter()]
    [switch]$SkipTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

#region Color Output

# Detect if colors should be disabled (CI environments, NO_COLOR standard)
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

#region Path Resolution

# Get repository root
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path $RepoRoot)) {
    Write-Status 'FAIL' "Invalid repository root: $RepoRoot"
    exit 2
}

# Resolve script paths
$ScriptPaths = @{
    SessionEnd = Join-Path $RepoRoot "scripts" "Validate-SessionEnd.ps1"
    PesterTests = Join-Path $RepoRoot "build" "scripts" "Invoke-PesterTests.ps1"
    PathNormalization = Join-Path $RepoRoot "build" "scripts" "Validate-PathNormalization.ps1"
    PlanningArtifacts = Join-Path $RepoRoot "build" "scripts" "Validate-PlanningArtifacts.ps1"
    AgentDrift = Join-Path $RepoRoot "build" "scripts" "Detect-AgentDrift.ps1"
}

#endregion

#region Validation State

$ValidationResults = @()
$StartTime = Get-Date
$TotalValidations = 0
$PassedValidations = 0
$FailedValidations = 0
$SkippedValidations = 0

#endregion

#region Helper Functions

function Invoke-Validation {
    <#
    .SYNOPSIS
        Runs a validation and tracks results.
    #>
    param(
        [string]$Name,
        [scriptblock]$ScriptBlock,
        [bool]$SkipCondition = $false
    )

    $script:TotalValidations++

    if ($SkipCondition) {
        Write-Status 'SKIP' "$Name (skipped due to -Quick flag)"
        $script:SkippedValidations++
        $script:ValidationResults += [PSCustomObject]@{
            Name = $Name
            Status = 'SKIP'
            Duration = 0
            Message = 'Skipped'
        }
        return $true
    }

    Write-Host ""
    Write-ColorOutput "=== $Name ===" $ColorCyan
    Write-Status 'RUNNING' "Starting validation..."

    $validationStart = Get-Date
    $success = $false
    $message = ""

    try {
        & $ScriptBlock
        $success = $?
        if ($success) {
            $message = "Validation passed"
            $script:PassedValidations++
        } else {
            $message = "Validation failed"
            $script:FailedValidations++
        }
    } catch {
        $success = $false
        $message = "Validation error: $($_.Exception.Message)"
        $script:FailedValidations++
    }

    $validationEnd = Get-Date
    $duration = ($validationEnd - $validationStart).TotalSeconds

    $script:ValidationResults += [PSCustomObject]@{
        Name = $Name
        Status = if ($success) { 'PASS' } else { 'FAIL' }
        Duration = $duration
        Message = $message
    }

    Write-Host ""
    if ($success) {
        Write-Status 'PASS' "$Name completed in $($duration.ToString('F2'))s"
    } else {
        Write-Status 'FAIL' "$Name failed after $($duration.ToString('F2'))s"
        Write-ColorOutput "Error: $message" $ColorRed
    }

    return $success
}

function Get-LatestSessionLog {
    <#
    .SYNOPSIS
        Finds the most recent session log in .agents/sessions/
    #>
    $sessionsPath = Join-Path $RepoRoot ".agents" "sessions"

    if (-not (Test-Path $sessionsPath)) {
        return $null
    }

    $sessionLogs = Get-ChildItem -Path $sessionsPath -Filter "*.md" -File |
        Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}-session-\d+.*\.md$' } |
        Sort-Object Name -Descending |
        Select-Object -First 1

    return $sessionLogs
}

#endregion

#region Header

Write-Host ""
Write-ColorOutput "=== Pre-PR Validation Runner ===" $ColorMagenta
Write-Host "Repository: $RepoRoot"
Write-Host "Mode: $(if ($Quick) { 'Quick (fast checks only)' } else { 'Full' })"
Write-Host "Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host ""

#endregion

#region Validation 1: Session End

Invoke-Validation -Name "Session End Validation" -ScriptBlock {
    $sessionLog = Get-LatestSessionLog

    if (-not $sessionLog) {
        Write-Status 'WARNING' "No session log found in .agents/sessions/"
        Write-Host "  If this is an agent session, create a session log."
        Write-Host "  If this is a manual commit, this check can be skipped."
        return $true  # Non-blocking for manual commits
    }

    Write-Host "Latest session log: $($sessionLog.Name)"

    if (-not (Test-Path $ScriptPaths.SessionEnd)) {
        Write-Status 'FAIL' "Validate-SessionEnd.ps1 not found"
        return $false
    }

    # Run session end validation
    & pwsh -NoProfile -File $ScriptPaths.SessionEnd -SessionLogPath $sessionLog.FullName

    return $LASTEXITCODE -eq 0
} | Out-Null

#endregion

#region Validation 2: Pester Tests

if (-not $SkipTests) {
    Invoke-Validation -Name "Pester Unit Tests" -ScriptBlock {
        if (-not (Test-Path $ScriptPaths.PesterTests)) {
            Write-Status 'FAIL' "Invoke-PesterTests.ps1 not found"
            return $false
        }

        # Run Pester tests
        $verbosityFlag = if ($PSCmdlet.MyInvocation.BoundParameters['Verbose']) { 'Diagnostic' } else { 'Normal' }
        & pwsh -NoProfile -File $ScriptPaths.PesterTests -Verbosity $verbosityFlag

        return $LASTEXITCODE -eq 0
    } | Out-Null
} else {
    Write-Status 'SKIP' "Pester Unit Tests (skipped via -SkipTests)"
    $script:TotalValidations++
    $script:SkippedValidations++
}

#endregion

#region Validation 3: Markdown Lint

Invoke-Validation -Name "Markdown Linting" -ScriptBlock {
    # Check for npx
    if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
        Write-Status 'FAIL' "npx not found (Node.js required)"
        Write-Host "  Install Node.js: https://nodejs.org/"
        return $false
    }

    Write-Host "Auto-fixing markdown files..."
    & npx markdownlint-cli2 --fix "**/*.md"

    if ($LASTEXITCODE -ne 0) {
        Write-Status 'FAIL' "Markdown linting failed (some issues cannot be auto-fixed)"
        Write-Host ""
        Write-Host "Common unfixable issues:"
        Write-Host "  - MD040: Add language identifier to code blocks"
        Write-Host "  - MD033: Wrap generic types like ArrayPool<T> in backticks"
        return $false
    }

    return $true
} | Out-Null

#endregion

#region Validation 4: Path Normalization (skip if -Quick)

Invoke-Validation -Name "Path Normalization" -SkipCondition $Quick -ScriptBlock {
    if (-not (Test-Path $ScriptPaths.PathNormalization)) {
        Write-Status 'FAIL' "Validate-PathNormalization.ps1 not found"
        return $false
    }

    & pwsh -NoProfile -File $ScriptPaths.PathNormalization -FailOnViolation

    return $LASTEXITCODE -eq 0
} | Out-Null

#endregion

#region Validation 5: Planning Artifacts (skip if -Quick)

Invoke-Validation -Name "Planning Artifacts" -SkipCondition $Quick -ScriptBlock {
    if (-not (Test-Path $ScriptPaths.PlanningArtifacts)) {
        Write-Status 'FAIL' "Validate-PlanningArtifacts.ps1 not found"
        return $false
    }

    & pwsh -NoProfile -File $ScriptPaths.PlanningArtifacts -FailOnError

    return $LASTEXITCODE -eq 0
} | Out-Null

#endregion

#region Validation 6: Agent Drift (skip if -Quick)

Invoke-Validation -Name "Agent Drift Detection" -SkipCondition $Quick -ScriptBlock {
    if (-not (Test-Path $ScriptPaths.AgentDrift)) {
        Write-Status 'FAIL' "Detect-AgentDrift.ps1 not found"
        return $false
    }

    & pwsh -NoProfile -File $ScriptPaths.AgentDrift

    return $LASTEXITCODE -eq 0
} | Out-Null

#endregion

#region Summary

$EndTime = Get-Date
$TotalDuration = ($EndTime - $StartTime).TotalSeconds

Write-Host ""
Write-ColorOutput "=== Validation Summary ===" $ColorMagenta
Write-Host "Duration: $($TotalDuration.ToString('F2'))s"
Write-Host "Total Validations: $TotalValidations"
Write-ColorOutput "Passed: $PassedValidations" $ColorGreen
Write-ColorOutput "Failed: $FailedValidations" $(if ($FailedValidations -gt 0) { $ColorRed } else { $ColorGreen })
Write-ColorOutput "Skipped: $SkippedValidations" $ColorCyan
Write-Host ""

# Detailed results
Write-ColorOutput "=== Detailed Results ===" $ColorCyan
Write-Host ""

foreach ($result in $ValidationResults) {
    $status = $result.Status
    $color = switch ($status) {
        'PASS' { $ColorGreen }
        'FAIL' { $ColorRed }
        'SKIP' { $ColorCyan }
        default { $ColorReset }
    }

    $durationStr = if ($result.Duration -gt 0) { " ($($result.Duration.ToString('F2'))s)" } else { "" }
    Write-ColorOutput "[$status] $($result.Name)$durationStr" $color
}

Write-Host ""

# Final verdict
if ($FailedValidations -gt 0) {
    Write-ColorOutput "RESULT: $FailedValidations validation(s) failed" $ColorRed
    Write-Host ""
    Write-Host "Fix suggestions:"
    Write-Host "  1. Review error messages above for specific issues"
    Write-Host "  2. Run individual validation scripts for more details"
    Write-Host "  3. See .agents/SHIFT-LEFT.md for workflow documentation"
    Write-Host ""
    exit 1
} else {
    Write-ColorOutput "RESULT: All validations passed" $ColorGreen
    Write-Host ""
    Write-Host "Ready to create pull request!"
    Write-Host ""
    exit 0
}

#endregion
