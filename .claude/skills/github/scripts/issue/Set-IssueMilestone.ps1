<#
.SYNOPSIS
    Assigns a milestone to a GitHub Issue.

.DESCRIPTION
    Manages milestone assignment:
    - Validates milestone exists before assigning
    - Optionally clears existing milestone

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER Issue
    Issue number (required).

.PARAMETER Milestone
    Milestone title to assign (required unless -Clear).

.PARAMETER Clear
    If specified, removes any existing milestone.

.PARAMETER Force
    If specified, replaces existing milestone.

.EXAMPLE
    .\Set-IssueMilestone.ps1 -Issue 123 -Milestone "v1.0.0"
    .\Set-IssueMilestone.ps1 -Issue 123 -Clear

.NOTES
    Exit Codes: 0=Success, 1=Invalid params, 2=Milestone not found, 3=API error, 4=Not authenticated, 5=Has milestone (use -Force)
#>

[CmdletBinding(DefaultParameterSetName = 'Assign')]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [int]$Issue,
    [Parameter(ParameterSetName = 'Assign', Mandatory)] [string]$Milestone,
    [Parameter(ParameterSetName = 'Clear')] [switch]$Clear,
    [Parameter(ParameterSetName = 'Assign')] [switch]$Force
)

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

# Get current milestone
$issueData = gh api "repos/$Owner/$Repo/issues/$Issue" --jq '.milestone.title' 2>$null
$currentMilestone = if ($LASTEXITCODE -eq 0 -and $issueData -ne 'null' -and -not [string]::IsNullOrWhiteSpace($issueData)) { $issueData } else { $null }

$output = [PSCustomObject]@{
    Success           = $false
    Issue             = $Issue
    Milestone         = $null
    PreviousMilestone = $currentMilestone
    Action            = 'none'
}

if ($Clear) {
    if (-not $currentMilestone) {
        Write-Host "Issue #$Issue has no milestone to clear." -ForegroundColor Yellow
        $output.Success = $true; $output.Action = 'no_change'
        Write-Output $output
        if ($env:GITHUB_OUTPUT) {
            Add-Content -Path $env:GITHUB_OUTPUT -Value "success=true"
            Add-Content -Path $env:GITHUB_OUTPUT -Value "issue=$Issue"
            Add-Content -Path $env:GITHUB_OUTPUT -Value "action=no_change"
        }
        exit 0
    }
    $null = gh api "repos/$Owner/$Repo/issues/$Issue" -X PATCH -f milestone= 2>&1
    if ($LASTEXITCODE -ne 0) { Write-ErrorAndExit "Failed to clear milestone" 3 }
    Write-Host "Cleared milestone from issue #$Issue" -ForegroundColor Green
    $output.Success = $true; $output.Action = 'cleared'
    Write-Output $output
    if ($env:GITHUB_OUTPUT) {
        Add-Content -Path $env:GITHUB_OUTPUT -Value "success=true"
        Add-Content -Path $env:GITHUB_OUTPUT -Value "issue=$Issue"
        Add-Content -Path $env:GITHUB_OUTPUT -Value "action=cleared"
        Add-Content -Path $env:GITHUB_OUTPUT -Value "previous_milestone=$currentMilestone"
    }
    exit 0
}

# Check milestone exists
$milestones = gh api "repos/$Owner/$Repo/milestones" --jq '.[].title' 2>$null
if ($LASTEXITCODE -ne 0 -or $milestones -notcontains $Milestone) {
    Write-ErrorAndExit "Milestone '$Milestone' does not exist in $Owner/$Repo." 2
}

# Check current
if ($currentMilestone -eq $Milestone) {
    Write-Host "Issue #$Issue already has milestone '$Milestone'." -ForegroundColor Yellow
    $output.Success = $true; $output.Milestone = $Milestone; $output.Action = 'no_change'
    Write-Output $output
    if ($env:GITHUB_OUTPUT) {
        Add-Content -Path $env:GITHUB_OUTPUT -Value "success=true"
        Add-Content -Path $env:GITHUB_OUTPUT -Value "issue=$Issue"
        Add-Content -Path $env:GITHUB_OUTPUT -Value "milestone=$Milestone"
        Add-Content -Path $env:GITHUB_OUTPUT -Value "action=no_change"
    }
    exit 0
}

if ($currentMilestone -and -not $Force) {
    Write-ErrorAndExit "Issue #$Issue already has milestone '$currentMilestone'. Use -Force to override." 5
}

# Assign
$null = gh issue edit $Issue --repo "$Owner/$Repo" --milestone $Milestone 2>&1
if ($LASTEXITCODE -ne 0) { Write-ErrorAndExit "Failed to set milestone" 3 }

$action = if ($currentMilestone) { 'replaced' } else { 'assigned' }
Write-Host "Set milestone '$Milestone' on issue #$Issue" -ForegroundColor Green
$output.Success = $true; $output.Milestone = $Milestone; $output.Action = $action
Write-Output $output
if ($env:GITHUB_OUTPUT) {
    Add-Content -Path $env:GITHUB_OUTPUT -Value "success=true"
    Add-Content -Path $env:GITHUB_OUTPUT -Value "issue=$Issue"
    Add-Content -Path $env:GITHUB_OUTPUT -Value "milestone=$Milestone"
    Add-Content -Path $env:GITHUB_OUTPUT -Value "action=$action"
    if ($currentMilestone) {
        Add-Content -Path $env:GITHUB_OUTPUT -Value "previous_milestone=$currentMilestone"
    }
}
