#!/usr/bin/env pwsh
<#
.SYNOPSIS
    [DEPRECATED] Thin wrapper for Get-UnresolvedReviewThreads from GitHubCore.psm1.

.DESCRIPTION
    This script is maintained for backward compatibility. New code should import
    GitHubCore.ps1 and call Get-UnresolvedReviewThreads directly.

    Per ADR-006, shared functions belong in modules, not dot-sourced scripts.

    Uses GitHub GraphQL API to query review thread resolution status.
    Part of the "Acknowledged vs Resolved" lifecycle model:

    NEW -> ACKNOWLEDGED (eyes reaction) -> REPLIED -> RESOLVED (thread marked resolved)

    See: .agents/architecture/bot-author-feedback-protocol.md

.PARAMETER Owner
    Repository owner. Auto-detected from git remote if not specified.

.PARAMETER Repo
    Repository name. Auto-detected from git remote if not specified.

.PARAMETER PullRequest
    Pull request number.

.OUTPUTS
    Array of thread objects where isResolved = false.
    Each object contains: id, isResolved, comments (first comment with databaseId).
    Returns empty array when all threads are resolved or on API failure.
    Never returns $null (per Skill-PowerShell-002).

.EXAMPLE
    ./Get-UnresolvedReviewThreads.ps1 -PullRequest 365
    # Returns unresolved threads for PR #365

.EXAMPLE
    # Preferred: Use module directly
    Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubCore.psm1") -Force
    $threads = Get-UnresolvedReviewThreads -Owner "rjmurillo" -Repo "ai-agents" -PullRequest 365

.NOTES
    GraphQL query handles up to 100 threads per request.
    Pagination not implemented for edge cases with 100+ threads.

    DEPRECATED: Use GitHubCore.psm1 module directly.
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)]
    [int]$PullRequest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Import GitHubCore module
$modulePath = Join-Path $PSScriptRoot ".." ".." "modules" "GitHubCore.psm1"
Import-Module $modulePath -Force

# Auto-detect repo info if not provided
if (-not $Owner -or -not $Repo) {
    $repoInfo = Get-RepoInfo  # From GitHubCore.psm1
    if ($null -eq $repoInfo) {
        Write-Error "Not in a git repository or no origin remote found" -ErrorAction Stop
    }
    if (-not $Owner) { $Owner = $repoInfo.Owner }
    if (-not $Repo) { $Repo = $repoInfo.Repo }
}

# Call module function
$threads = Get-UnresolvedReviewThreads -Owner $Owner -Repo $Repo -PullRequest $PullRequest

# Output as JSON for machine consumption
$threads | ConvertTo-Json -Depth 5
