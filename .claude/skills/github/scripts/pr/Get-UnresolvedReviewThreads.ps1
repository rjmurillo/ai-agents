#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Retrieves review threads that remain unresolved on a pull request.

.DESCRIPTION
    Uses GitHub GraphQL API to query review thread resolution status.
    Part of the "Acknowledged vs Resolved" lifecycle model:

    NEW -> ACKNOWLEDGED (eyes reaction) -> REPLIED -> RESOLVED (thread marked resolved)

    A comment can be acknowledged (has eyes reaction) but NOT resolved (thread still open).
    This function identifies threads in that intermediate state.

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
    $threads = ./Get-UnresolvedReviewThreads.ps1 -PullRequest 365
    if ($threads.Count -gt 0) {
        Write-Host "Found $($threads.Count) unresolved threads"
    }

.NOTES
    GraphQL query handles up to 100 threads per request.
    Pagination not implemented for edge cases with 100+ threads.
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

#region Helpers

function Get-RepoInfo {
    [CmdletBinding()]
    param()
    $remote = git remote get-url origin 2>$null
    if (-not $remote) {
        throw "Not in a git repository or no origin remote"
    }

    if ($remote -match 'github\.com[:/]([^/]+)/([^/.]+)') {
        return @{
            Owner = $Matches[1]
            Repo = $Matches[2] -replace '\.git$', ''
        }
    }

    throw "Could not parse GitHub repository from remote: $remote"
}

#endregion

#region Main Logic

function Get-UnresolvedReviewThreads {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Owner,

        [Parameter(Mandatory)]
        [string]$Repo,

        [Parameter(Mandatory)]
        [int]$PR
    )

    # GraphQL query per FR1 specification
    # Note: first: 100 handles most PRs; pagination not implemented for edge cases with 100+ threads
    $query = @"
query {
    repository(owner: "$Owner", name: "$Repo") {
        pullRequest(number: $PR) {
            reviewThreads(first: 100) {
                nodes {
                    id
                    isResolved
                    comments(first: 1) {
                        nodes {
                            databaseId
                        }
                    }
                }
            }
        }
    }
}
"@

    $result = gh api graphql -f query=$query 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Failed to query review threads for PR #${PR}: $result"
        return @()  # Return empty array on failure per FR2
    }

    try {
        $parsed = $result | ConvertFrom-Json
    }
    catch {
        Write-Warning "Failed to parse GraphQL response for PR #${PR}: $result"
        return @()  # Return empty array on parse failure
    }

    $threads = $parsed.data.repository.pullRequest.reviewThreads.nodes

    if ($null -eq $threads -or $threads.Count -eq 0) {
        return @()  # No threads exist
    }

    # Filter to unresolved threads only
    $unresolved = @($threads | Where-Object { -not $_.isResolved })

    return $unresolved  # Always returns array, never $null
}

#endregion

#region Entry Point

# Guard: Only execute main logic when run directly, not when dot-sourced for testing
if ($MyInvocation.InvocationName -eq '.') {
    return
}

# Auto-detect repo info if not provided
if (-not $Owner -or -not $Repo) {
    $repoInfo = Get-RepoInfo
    if (-not $Owner) { $Owner = $repoInfo.Owner }
    if (-not $Repo) { $Repo = $repoInfo.Repo }
}

# Get unresolved threads
$threads = Get-UnresolvedReviewThreads -Owner $Owner -Repo $Repo -PR $PullRequest

# Output as JSON for machine consumption
$threads | ConvertTo-Json -Depth 5

#endregion
