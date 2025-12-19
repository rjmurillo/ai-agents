<#
.SYNOPSIS
    Applies labels to a GitHub Issue with auto-creation support.

.DESCRIPTION
    Manages labels on GitHub Issues:
    - Creates labels if they don't exist
    - Applies multiple labels to an issue
    - Supports priority labels with standard formatting

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER Issue
    Issue number (required).

.PARAMETER Labels
    Array of label names to apply.

.PARAMETER Priority
    Priority level (P0, P1, P2, P3). Creates "priority:PX" label.

.PARAMETER CreateMissing
    If specified, creates labels that don't exist (default: true).

.PARAMETER DefaultColor
    Default color for auto-created labels (default: "ededed").

.PARAMETER PriorityColor
    Color for priority labels (default: "FFA500").

.EXAMPLE
    .\Set-IssueLabels.ps1 -Issue 123 -Labels @("bug", "needs-review")
    .\Set-IssueLabels.ps1 -Issue 123 -Labels @("enhancement") -Priority "P1"

.NOTES
    Exit Codes: 0=Success, 1=Invalid params, 3=API error, 4=Not authenticated
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [int]$Issue,
    [string[]]$Labels = @(),
    [ValidateSet("P0", "P1", "P2", "P3", "")] [string]$Priority,
    [switch]$CreateMissing = $true,
    [string]$DefaultColor = "ededed",
    [string]$PriorityColor = "FFA500"
)

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

# Build label list
$allLabels = [System.Collections.Generic.List[hashtable]]::new()
foreach ($label in $Labels) {
    if (-not [string]::IsNullOrWhiteSpace($label)) {
        $allLabels.Add(@{ Name = $label.Trim(); Color = $DefaultColor })
    }
}
if (-not [string]::IsNullOrWhiteSpace($Priority)) {
    $allLabels.Add(@{ Name = "priority:$Priority"; Color = $PriorityColor })
}

if ($allLabels.Count -eq 0) {
    Write-Warning "No labels to apply."
    exit 0
}

$applied = @(); $created = @(); $failed = @()

foreach ($labelInfo in $allLabels) {
    $labelName = $labelInfo.Name
    $labelColor = $labelInfo.Color

    # Check existence
    $null = gh api "repos/$Owner/$Repo/labels/$([Uri]::EscapeDataString($labelName))" 2>$null
    $exists = $LASTEXITCODE -eq 0

    if (-not $exists) {
        if ($CreateMissing) {
            $null = gh api "repos/$Owner/$Repo/labels" -X POST -f name=$labelName -f color=$labelColor -f description="Auto-created by AI triage" 2>&1
            if ($LASTEXITCODE -eq 0) { $created += $labelName }
            else { $failed += $labelName; continue }
        }
        else { continue }
    }

    $null = gh issue edit $Issue --repo "$Owner/$Repo" --add-label $labelName 2>&1
    if ($LASTEXITCODE -eq 0) { $applied += $labelName }
    else { $failed += $labelName }
}

$output = [PSCustomObject]@{
    Success      = $failed.Count -eq 0
    Issue        = $Issue
    Applied      = $applied
    Created      = $created
    Failed       = $failed
    TotalApplied = $applied.Count
}

Write-Output $output
if ($applied.Count -gt 0) { Write-Host "Applied $($applied.Count) label(s) to issue #$Issue: $($applied -join ', ')" -ForegroundColor Green }
if ($failed.Count -gt 0) { Write-Host "Failed: $($failed -join ', ')" -ForegroundColor Red; exit 3 }
