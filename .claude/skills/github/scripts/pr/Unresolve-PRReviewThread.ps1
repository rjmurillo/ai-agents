<#
.SYNOPSIS
    Unresolves a PR review thread using GitHub GraphQL API.

.DESCRIPTION
    Marks a previously resolved PR review thread as unresolved (re-opens it).
    This is the counterpart to Resolve-PRReviewThread.ps1.

    Use this when a resolved thread needs to be re-opened for further
    discussion or when the resolution was premature.

.PARAMETER ThreadId
    The global GraphQL ID of the review thread (e.g., PRRT_kwDOQoWRls5m7ln8).

.PARAMETER PullRequest
    The PR number. Used with -All to unresolve all resolved threads.

.PARAMETER All
    Unresolve all resolved threads on the specified PR.

.EXAMPLE
    ./Unresolve-PRReviewThread.ps1 -ThreadId "PRRT_kwDOQoWRls5m7ln8"

.EXAMPLE
    ./Unresolve-PRReviewThread.ps1 -PullRequest 225 -All

.NOTES
    Exit Codes:
        0 - Success
        1 - Operation failed or invalid parameters
        2 - Thread/PR not found
        3 - API error
        4 - Not authenticated

    Requires write access to the repository.
    
    See: ADR-035 Exit Code Standardization
#>

[CmdletBinding(DefaultParameterSetName = 'Single')]
param(
    [Parameter(Mandatory, ParameterSetName = 'Single')]
    [string]$ThreadId,

    [Parameter(Mandatory, ParameterSetName = 'All')]
    [int]$PullRequest,

    [Parameter(ParameterSetName = 'All')]
    [switch]$All
)

$ErrorActionPreference = 'Stop'

# Import shared helpers
Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubCore.psm1") -Force

#region Helper Functions

function Invoke-UnresolveThread {
    param([string]$Id)

    # Uses GraphQL variables for security (prevents injection via ThreadId)
    $mutation = @'
mutation($threadId: ID!) {
    unresolveReviewThread(input: {threadId: $threadId}) {
        thread {
            id
            isResolved
        }
    }
}
'@

    $result = gh api graphql -f query=$mutation -f threadId="$Id" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Failed to unresolve thread ${Id}: $result"
        return $false
    }

    try {
        $parsed = $result | ConvertFrom-Json
        # Explicit null check to prevent false positives when API returns malformed response
        $thread = $parsed.data.unresolveReviewThread.thread
        if ($null -ne $thread -and $thread.isResolved -eq $false) {
            Write-Host "Unresolved thread: $Id" -ForegroundColor Green
            return $true
        } else {
            Write-Warning "Thread $Id may not have been unresolved. Response: $result"
            return $false
        }
    }
    catch {
        Write-Warning "Failed to parse GraphQL response for thread $Id. Raw response: $result"
        return $false
    }
}

function Get-ResolvedReviewThreads {
    param([int]$PR)

    # Get repo info
    $repoJson = gh repo view --json owner,name 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to get repo info: $repoJson"
    }
    $repo = $repoJson | ConvertFrom-Json

    # Uses GraphQL variables for security (prevents injection via owner/name/PR)
    $query = @'
query($owner: String!, $name: String!, $prNumber: Int!) {
    repository(owner: $owner, name: $name) {
        pullRequest(number: $prNumber) {
            reviewThreads(first: 100) {
                nodes {
                    id
                    isResolved
                    comments(first: 1) {
                        nodes {
                            databaseId
                            author { login }
                        }
                    }
                }
            }
        }
    }
}
'@

    $result = gh api graphql -f query=$query -f owner="$($repo.owner.login)" -f name="$($repo.name)" -F prNumber=$PR 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to query threads: $result"
    }

    try {
        $parsed = $result | ConvertFrom-Json
    }
    catch {
        throw "Failed to parse GraphQL response when querying threads. Raw response: $result"
    }
    $threads = $parsed.data.repository.pullRequest.reviewThreads.nodes

    # Return only resolved threads (opposite of Get-UnresolvedReviewThreads)
    return $threads | Where-Object { $_.isResolved }
}

#endregion

#region Validation

# Parameter validation first (before external checks per Skill-Testing-Exit-Code-Order-001)
if ($PSCmdlet.ParameterSetName -eq 'Single') {
    if ([string]::IsNullOrWhiteSpace($ThreadId)) {
        Write-ErrorAndExit "ThreadId parameter is required." 1
    }
    if (-not ($ThreadId -match '^PRRT_')) {
        Write-ErrorAndExit "Invalid ThreadId format. Expected PRRT_... format." 1
    }
}

# External tool check
Assert-GhAuthenticated

#endregion

#region Main Execution

if ($PSCmdlet.ParameterSetName -eq 'Single') {
    $success = Invoke-UnresolveThread -Id $ThreadId

    # Output structured result
    [PSCustomObject]@{
        Success = $success
        ThreadId = $ThreadId
        Action = "unresolve"
    } | ConvertTo-Json

    exit ($success ? 0 : 1)
}
else {
    # Unresolve all resolved threads
    $resolvedThreads = Get-ResolvedReviewThreads -PR $PullRequest

    if (-not $resolvedThreads) {
        Write-Host "No resolved threads on PR #${PullRequest} to unresolve" -ForegroundColor Green

        [PSCustomObject]@{
            TotalResolved = 0
            Unresolved = 0
            Failed = 0
            Success = $true
        } | ConvertTo-Json

        exit 0
    }

    Write-Host "Found $($resolvedThreads.Count) resolved thread(s) on PR #${PullRequest}" -ForegroundColor Cyan

    $unresolved = 0
    $failed = 0

    foreach ($thread in $resolvedThreads) {
        # Safely derive author and comment ID; threads may exist without comments
        $author = "<unknown>"
        $commentId = "<unknown>"

        if ($thread.comments -and $thread.comments.nodes -and $thread.comments.nodes.Count -gt 0 -and $thread.comments.nodes[0]) {
            $firstComment = $thread.comments.nodes[0]

            if ($firstComment.author -and $firstComment.author.login) {
                $author = $firstComment.author.login
            }

            if ($firstComment.databaseId) {
                $commentId = $firstComment.databaseId
            }
        }

        Write-Host "  Unresolving thread $($thread.id) (comment $commentId by @$author)..." -ForegroundColor Yellow

        if (Invoke-UnresolveThread -Id $thread.id) {
            $unresolved++
        } else {
            $failed++
        }
    }

    Write-Host ""
    Write-Host "Summary: $unresolved unresolved, $failed failed" -ForegroundColor $(if ($failed -eq 0) { 'Green' } else { 'Yellow' })

    # Return results as JSON for parsing
    [PSCustomObject]@{
        TotalResolved = $resolvedThreads.Count
        Unresolved = $unresolved
        Failed = $failed
        Success = ($failed -eq 0)
    } | ConvertTo-Json

    exit ($failed -eq 0 ? 0 : 1)
}

#endregion
