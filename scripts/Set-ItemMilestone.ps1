#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Assigns milestone to PR or issue if none exists.

.DESCRIPTION
    Orchestrates milestone assignment for GitHub PRs and issues:
    1. Checks if item already has a milestone (skips if present)
    2. Auto-detects latest semantic version milestone (unless -MilestoneTitle provided)
    3. Delegates to Set-IssueMilestone.ps1 skill for actual assignment

    Used by milestone-tracking workflow to auto-assign milestones on merge/close events.

.PARAMETER ItemType
    Type of item: "pr" or "issue" (required).

.PARAMETER ItemNumber
    PR or issue number (required).

.PARAMETER Owner
    Repository owner (optional, can be inferred from git remote).

.PARAMETER Repo
    Repository name (optional, can be inferred from git remote).

.PARAMETER MilestoneTitle
    Specific milestone to assign. If not provided, auto-detects latest semantic version.

.OUTPUTS
    PSCustomObject with properties:
    - Success: Boolean indicating success
    - ItemType: "pr" or "issue"
    - ItemNumber: PR/issue number
    - Milestone: Assigned milestone title
    - Action: "assigned", "skipped" (already had milestone), "failed"
    - Message: Human-readable status message

    Output to GITHUB_OUTPUT (if running in CI):
    - success=true/false
    - item_type=pr|issue
    - item_number=N
    - milestone=X.Y.Z
    - action=assigned|skipped|failed
    - message=Status message

.EXAMPLE
    ./Set-ItemMilestone.ps1 -ItemType pr -ItemNumber 123
    Auto-assigns latest semantic milestone to PR #123 if it has none.

.EXAMPLE
    ./Set-ItemMilestone.ps1 -ItemType issue -ItemNumber 456 -MilestoneTitle "0.2.0"
    Assigns specific milestone "0.2.0" to issue #456 if it has none.

.NOTES
    Exit codes (per ADR-035):
    - 0: Success (assigned or skipped)
    - 1: Invalid parameters
    - 2: Milestone detection failed
    - 3: API error
    - 5: Assignment failed

    GitHub API treats PRs as issues for most operations, so the same
    Set-IssueMilestone.ps1 skill works for both.

.LINK
    .github/workflows/milestone-tracking.yml
    scripts/Get-LatestSemanticMilestone.ps1
    .claude/skills/github/scripts/issue/Set-IssueMilestone.ps1
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet("pr", "issue")]
    [string]$ItemType,

    [Parameter(Mandatory)]
    [int]$ItemNumber,

    [Parameter()]
    [string]$Owner,

    [Parameter()]
    [string]$Repo,

    [Parameter()]
    [string]$MilestoneTitle
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Import shared GitHub functions
$modulePath = Join-Path $PSScriptRoot ".." ".claude" "skills" "github" "modules" "GitHubCore.psm1"
if (-not (Test-Path $modulePath)) {
    Write-Error "GitHubCore module not found at: $modulePath"
    exit 1
}
Import-Module $modulePath -Force

function Write-OutputSummary {
    param(
        [PSCustomObject]$Result
    )

    # Write to GITHUB_OUTPUT
    if ($env:GITHUB_OUTPUT) {
        "success=$($Result.Success.ToString().ToLower())" | Out-File $env:GITHUB_OUTPUT -Append -Encoding utf8
        "item_type=$($Result.ItemType)" | Out-File $env:GITHUB_OUTPUT -Append -Encoding utf8
        "item_number=$($Result.ItemNumber)" | Out-File $env:GITHUB_OUTPUT -Append -Encoding utf8
        "milestone=$($Result.Milestone)" | Out-File $env:GITHUB_OUTPUT -Append -Encoding utf8
        "action=$($Result.Action)" | Out-File $env:GITHUB_OUTPUT -Append -Encoding utf8
        "message=$($Result.Message)" | Out-File $env:GITHUB_OUTPUT -Append -Encoding utf8
    }

    # Write step summary
    if ($env:GITHUB_STEP_SUMMARY) {
        $icon = if ($Result.Success) { "✅" } else { "❌" }
        $itemLabel = if ($Result.ItemType -eq "pr") { "Pull Request" } else { "Issue" }

        @"
## Milestone Assignment Result

**Status**: $icon $($Result.Action.ToUpper())

**$itemLabel**: #$($Result.ItemNumber)
**Milestone**: $($Result.Milestone)

$($Result.Message)
"@ | Out-File $env:GITHUB_STEP_SUMMARY -Append -Encoding utf8
    }
}

try {
    # Verify GitHub CLI authentication
    Assert-GhAuthenticated

    # Resolve repository parameters
    $resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
    $Owner = $resolved.Owner
    $Repo = $resolved.Repo

    Write-Verbose "Processing $ItemType #$ItemNumber in $Owner/$Repo"

    # Check if item already has a milestone
    # GitHub API: PRs and issues share the same endpoint for milestone queries
    $itemEndpoint = "repos/$Owner/$Repo/issues/$ItemNumber"
    $itemDataJson = gh api $itemEndpoint 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorAndExit "Failed to query $ItemType #${ItemNumber}: $itemDataJson" 3
    }

    $itemData = $itemDataJson | ConvertFrom-Json

    if ($null -ne $itemData.milestone -and -not [string]::IsNullOrWhiteSpace($itemData.milestone.title)) {
        $existingMilestone = $itemData.milestone.title
        Write-Host "$ItemType #$ItemNumber already has milestone: $existingMilestone" -ForegroundColor Yellow

        $result = [PSCustomObject]@{
            Success     = $true
            ItemType    = $ItemType
            ItemNumber  = $ItemNumber
            Milestone   = $existingMilestone
            Action      = "skipped"
            Message     = "Already has milestone '$existingMilestone'. No action taken (preserving manual assignments)."
        }

        Write-OutputSummary $result
        Write-Output $result
        exit 0
    }

    # Item has no milestone, proceed with assignment

    # Determine milestone to assign
    if (-not $MilestoneTitle) {
        Write-Verbose "Milestone not specified, auto-detecting latest semantic version"

        $detectionScript = Join-Path $PSScriptRoot "Get-LatestSemanticMilestone.ps1"
        if (-not (Test-Path $detectionScript)) {
            Write-ErrorAndExit "Milestone detection script not found: $detectionScript" 2
        }

        $detectionResult = & $detectionScript -Owner $Owner -Repo $Repo 2>&1
        if ($LASTEXITCODE -ne 0 -or -not $detectionResult.Found) {
            Write-ErrorAndExit "Failed to detect latest semantic milestone. Create a semantic version milestone (e.g., 0.2.0) or specify -MilestoneTitle." 2
        }

        $MilestoneTitle = $detectionResult.Title
        Write-Verbose "Auto-detected milestone: $MilestoneTitle"
    }

    # Delegate to Set-IssueMilestone.ps1 skill
    $assignmentScript = Join-Path $PSScriptRoot ".." ".claude" "skills" "github" "scripts" "issue" "Set-IssueMilestone.ps1"
    if (-not (Test-Path $assignmentScript)) {
        Write-ErrorAndExit "Set-IssueMilestone skill not found: $assignmentScript" 2
    }

    Write-Host "Assigning milestone '$MilestoneTitle' to $ItemType #$ItemNumber" -ForegroundColor Cyan

    $assignmentResult = & $assignmentScript `
        -Owner $Owner `
        -Repo $Repo `
        -Issue $ItemNumber `
        -Milestone $MilestoneTitle 2>&1

    if ($LASTEXITCODE -ne 0 -or -not $assignmentResult.Success) {
        $errorMsg = if ($assignmentResult.Action -eq 'milestone_not_found') {
            "Milestone '$MilestoneTitle' does not exist in $Owner/$Repo"
        } else {
            "Failed to assign milestone: $assignmentResult"
        }
        Write-ErrorAndExit $errorMsg 5
    }

    Write-Host "Successfully assigned milestone '$MilestoneTitle' to $ItemType #$ItemNumber" -ForegroundColor Green

    $result = [PSCustomObject]@{
        Success     = $true
        ItemType    = $ItemType
        ItemNumber  = $ItemNumber
        Milestone   = $MilestoneTitle
        Action      = "assigned"
        Message     = "Assigned milestone '$MilestoneTitle' (auto-detected latest semantic version)."
    }

    Write-OutputSummary $result
    Write-Output $result
    exit 0
}
catch {
    $result = [PSCustomObject]@{
        Success     = $false
        ItemType    = $ItemType
        ItemNumber  = $ItemNumber
        Milestone   = ""
        Action      = "failed"
        Message     = "Error: $($_.Exception.Message)"
    }

    Write-OutputSummary $result
    Write-ErrorAndExit "Unexpected error: $($_.Exception.Message)" 3
}
