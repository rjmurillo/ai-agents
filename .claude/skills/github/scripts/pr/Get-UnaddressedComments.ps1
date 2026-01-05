#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Gets bot comments that are either unacknowledged OR acknowledged but unresolved.

.DESCRIPTION
    Detects comments in the NEW, ACKNOWLEDGED, or REPLIED lifecycle states.
    Captures the full spectrum of unaddressed feedback.

    Lifecycle Model:
      NEW (eyes=0) -> ACKNOWLEDGED (eyes>0) -> REPLIED -> RESOLVED (thread marked resolved)

    A comment is "addressed" ONLY when:
      - It has been acknowledged (eyes > 0) AND
      - Its thread has been resolved (isResolved = true)

    A comment is "unaddressed" when:
      - It lacks acknowledgment (eyes = 0), OR
      - It is acknowledged but its thread remains unresolved (eyes > 0, isResolved = false)

    Semantic Model:
      Get-UnacknowledgedComments: Detects [NEW] only (reactions.eyes = 0)
      Get-UnaddressedComments:    Detects [NEW], [ACKNOWLEDGED], [REPLIED] (all unresolved states)

    See: .agents/architecture/bot-author-feedback-protocol.md

.PARAMETER Owner
    Repository owner. Auto-detected from git remote if not specified.

.PARAMETER Repo
    Repository name. Auto-detected from git remote if not specified.

.PARAMETER PullRequest
    Pull request number.

.PARAMETER Comments
    Pre-fetched comments array. If not provided, will fetch using GitHub API.
    Pass this to avoid duplicate API calls when comments are already fetched.

.OUTPUTS
    Array of bot comments that are unaddressed.
    Returns empty array when all bot comments are addressed.
    Never returns $null (per Skill-PowerShell-002).

.EXAMPLE
    ./Get-UnaddressedComments.ps1 -PullRequest 365
    # Returns unaddressed bot comments for PR #365

.EXAMPLE
    # Reuse pre-fetched comments to avoid duplicate API calls
    $comments = gh api repos/owner/repo/pulls/365/comments | ConvertFrom-Json
    $unaddressed = ./Get-UnaddressedComments.ps1 -PullRequest 365 -Comments $comments

.NOTES
    Depends on Get-UnresolvedReviewThreads.ps1 for thread resolution status.
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)]
    [int]$PullRequest,
    [Parameter()]
    [array]$Comments = $null
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

function Get-PRComments {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Owner,

        [Parameter(Mandatory)]
        [string]$Repo,

        [Parameter(Mandatory)]
        [int]$PR
    )

    $endpoint = "repos/$Owner/$Repo/pulls/$PR/comments"
    $result = gh api $endpoint 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Failed to fetch PR comments for PR #${PR}: $result"
        return @()
    }

    try {
        $parsed = $result | ConvertFrom-Json
    }
    catch {
        Write-Warning "Failed to parse PR comments response for PR #${PR}: $result"
        return @()
    }

    if ($null -eq $parsed) {
        return @()
    }

    return @($parsed)
}

#endregion

#region Main Logic

function Get-UnaddressedComments {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Owner,

        [Parameter(Mandatory)]
        [string]$Repo,

        [Parameter(Mandatory)]
        [int]$PR,

        [Parameter()]
        [array]$Comments = $null
    )

    # Use pre-fetched comments if provided, otherwise fetch from API
    if ($null -eq $Comments) {
        $Comments = Get-PRComments -Owner $Owner -Repo $Repo -PR $PR
    }

    # Early exit if no comments
    if ($null -eq $Comments -or $Comments.Count -eq 0) {
        return @()
    }

    # Query unresolved threads to get IDs of comments that are acknowledged but not resolved
    # Dot-source the sibling script for thread lookup
    $scriptDir = $PSScriptRoot
    $threadsScript = Join-Path $scriptDir 'Get-UnresolvedReviewThreads.ps1'

    if (-not (Test-Path $threadsScript)) {
        Write-Warning "Get-UnresolvedReviewThreads.ps1 not found at $threadsScript"
        # Fall back to just checking eyes reactions (unacknowledged only)
        $unaddressed = @($Comments | Where-Object {
            $_.user.type -eq 'Bot' -and $_.reactions.eyes -eq 0
        })
        return $unaddressed
    }

    # Source and call the thread lookup
    . $threadsScript -Owner $Owner -Repo $Repo -PullRequest $PR
    $unresolvedThreads = Get-UnresolvedReviewThreads -Owner $Owner -Repo $Repo -PullRequest $PR

    # Extract comment IDs from unresolved threads (databaseId field from first comment in each thread)
    $unresolvedCommentIds = @()
    foreach ($thread in $unresolvedThreads) {
        $firstComment = $thread.comments.nodes | Select-Object -First 1
        if ($null -ne $firstComment -and $null -ne $firstComment.databaseId) {
            $unresolvedCommentIds += $firstComment.databaseId
        }
    }

    # Filter comments where:
    # - user.type = 'Bot' AND
    # - (reactions.eyes = 0 OR id in unresolvedCommentIds)
    #
    # This captures:
    # - NEW state: eyes = 0 (unacknowledged)
    # - ACKNOWLEDGED/REPLIED state: eyes > 0 but thread unresolved
    $unaddressed = @($Comments | Where-Object {
        $_.user.type -eq 'Bot' -and
        ($_.reactions.eyes -eq 0 -or $unresolvedCommentIds -contains $_.id)
    })

    if ($null -eq $unaddressed -or $unaddressed.Count -eq 0) {
        return @()
    }

    return $unaddressed
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

# Get unaddressed comments
$result = Get-UnaddressedComments -Owner $Owner -Repo $Repo -PR $PullRequest -Comments $Comments

# Output as JSON for machine consumption
$result | ConvertTo-Json -Depth 5

#endregion
