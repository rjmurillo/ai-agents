#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Detects the latest open semantic version milestone in a GitHub repository.

.DESCRIPTION
    Queries GitHub API for all open milestones, filters those matching semantic versioning
    format (X.Y.Z), sorts by version number using proper version comparison, and returns
    the latest milestone details.

    Used by milestone-tracking workflow to auto-assign milestones to merged PRs and closed issues.

.PARAMETER Owner
    Repository owner (optional, can be inferred from git remote).

.PARAMETER Repo
    Repository name (optional, can be inferred from git remote).

.NOTES
  EXIT CODES:
  0  - Success: Milestone found successfully
  1  - Error: Invalid parameters
  2  - Error: Config/resource error (module not found, no semantic milestones found)
  3  - Error: External error (API error)

  See: ADR-035 Exit Code Standardization

  Semantic version format: X.Y.Z where X, Y, Z are integers (e.g., "0.2.0", "1.10.3").
  Non-semantic milestones (e.g., "Future", "Backlog") are ignored.

.OUTPUTS
    PSCustomObject with properties:
    - Title: Milestone title (e.g., "0.2.0")
    - Number: Milestone number (GitHub API ID)
    - Found: Boolean indicating if semantic milestone was found

    Output to GITHUB_OUTPUT (if running in CI):
    - milestone_title=X.Y.Z
    - milestone_number=N
    - found=true/false

.EXAMPLE
    ./Get-LatestSemanticMilestone.ps1
    Detects latest semantic milestone in current repo (inferred from git remote).

.EXAMPLE
    ./Get-LatestSemanticMilestone.ps1 -Owner rjmurillo -Repo ai-agents
    Detects latest semantic milestone in specified repo.

.LINK
    .github/workflows/milestone-tracking.yml
    .claude/skills/github/scripts/issue/Set-IssueMilestone.ps1
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Owner,

    [Parameter()]
    [string]$Repo
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Import shared GitHub functions
$modulePath = Join-Path $PSScriptRoot ".." -AdditionalChildPath "..", "modules", "GitHubCore.psm1"
if (-not (Test-Path $modulePath)) {
    Write-Error "GitHubCore module not found at: $modulePath"
    exit 2
}
Import-Module $modulePath -Force

try {
    # Verify GitHub CLI authentication
    Assert-GhAuthenticated

    # Resolve repository parameters
    $resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
    $Owner = $resolved.Owner
    $Repo = $resolved.Repo

    Write-Verbose "Querying milestones for $Owner/$Repo"

    # Query all open milestones (with pagination to handle repositories with >100 milestones)
    $milestonesJson = gh api --paginate "repos/$Owner/$Repo/milestones?state=open&per_page=100" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorAndExit "Failed to query milestones from GitHub API: $milestonesJson" 3
    }

    # Parse JSON (safe now that we know the command succeeded)
    try {
        $milestones = $milestonesJson | ConvertFrom-Json
    }
    catch {
        Write-ErrorAndExit "Failed to parse milestone data as JSON: $($_.Exception.Message)" 3
    }

    if ($milestones.Count -eq 0) {
        Write-Warning "No open milestones found in $Owner/$Repo"
        $result = [PSCustomObject]@{
            Title  = ""
            Number = 0
            Found  = $false
        }

        # Output to GITHUB_OUTPUT if running in CI
        if ($env:GITHUB_OUTPUT) {
            "milestone_title=" >> $env:GITHUB_OUTPUT
            "milestone_number=0" >> $env:GITHUB_OUTPUT
            "found=false" >> $env:GITHUB_OUTPUT
        }

        # Write step summary
        if ($env:GITHUB_STEP_SUMMARY) {
            @"
## Milestone Detection Result

**Status**: ❌ No semantic version milestones found

No open milestones matching semantic versioning format (X.Y.Z) were found in **$Owner/$Repo**.

**Action**: Create a semantic version milestone (e.g., 0.2.0, 1.0.0) or close this workflow run.
"@ >> $env:GITHUB_STEP_SUMMARY
        }

        Write-Output $result
        exit 2
    }

    # Filter milestones matching semantic version format (X.Y.Z)
    $semanticPattern = '^\d+\.\d+\.\d+$'
    $semanticMilestones = $milestones | Where-Object { $_.title -match $semanticPattern }

    if ($semanticMilestones.Count -eq 0) {
        Write-Warning "No semantic version milestones found. Available milestones: $($milestones.title -join ', ')"
        $result = [PSCustomObject]@{
            Title  = ""
            Number = 0
            Found  = $false
        }

        # Output to GITHUB_OUTPUT
        if ($env:GITHUB_OUTPUT) {
            "milestone_title=" >> $env:GITHUB_OUTPUT
            "milestone_number=0" >> $env:GITHUB_OUTPUT
            "found=false" >> $env:GITHUB_OUTPUT
        }

        # Write step summary
        if ($env:GITHUB_STEP_SUMMARY) {
            $availableList = ($milestones | ForEach-Object { "- $($_.title)" }) -join "`n"
            @"
## Milestone Detection Result

**Status**: ❌ No semantic version milestones found

Found $($milestones.Count) open milestone(s), but none match semantic versioning format (X.Y.Z):

$availableList

**Action**: Create a semantic version milestone (e.g., 0.2.0, 1.0.0) or close this workflow run.
"@ >> $env:GITHUB_STEP_SUMMARY
        }

        Write-Output $result
        exit 2
    }

    # Sort by version using [System.Version] for proper comparison
    # (e.g., 0.10.0 > 0.2.0, not string comparison where "0.2.0" > "0.10.0")
    $latest = $semanticMilestones |
        Sort-Object -Property { [System.Version]$_.title } -Descending |
        Select-Object -First 1

    Write-Verbose "Latest semantic milestone: $($latest.title) (number: $($latest.number))"

    $result = [PSCustomObject]@{
        Title  = $latest.title
        Number = $latest.number
        Found  = $true
    }

    # Output to GITHUB_OUTPUT
    if ($env:GITHUB_OUTPUT) {
        "milestone_title=$($latest.title)" >> $env:GITHUB_OUTPUT
        "milestone_number=$($latest.number)" >> $env:GITHUB_OUTPUT
        "found=true" >> $env:GITHUB_OUTPUT
    }

    # Write step summary
    if ($env:GITHUB_STEP_SUMMARY) {
        @"
## Milestone Detection Result

**Status**: ✅ Found semantic version milestone

**Milestone**: $($latest.title) (ID: $($latest.number))

All $($semanticMilestones.Count) semantic version milestone(s) found:
$($semanticMilestones | ForEach-Object { "- **$($_.title)** (ID: $($_.number))" } | Out-String)
"@ >> $env:GITHUB_STEP_SUMMARY
    }

    Write-Output $result
    exit 0
}
catch {
    Write-ErrorAndExit "Unexpected error: $($_.Exception.Message)" 3
}
