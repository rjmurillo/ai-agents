<#
.SYNOPSIS
    Resolves a PR review thread using GitHub GraphQL API.

.DESCRIPTION
    Marks a PR review thread as resolved. This is required for PRs with branch
    protection rules that require all conversations to be resolved before merging.

.PARAMETER ThreadId
    The global GraphQL ID of the review thread (e.g., PRRT_kwDOQoWRls5m7ln8).

.PARAMETER PullRequest
    The PR number. Used with -All to resolve all unresolved threads.

.PARAMETER All
    Resolve all unresolved threads on the specified PR.

.EXAMPLE
    ./Resolve-PRReviewThread.ps1 -ThreadId "PRRT_kwDOQoWRls5m7ln8"

.EXAMPLE
    ./Resolve-PRReviewThread.ps1 -PullRequest 225 -All
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

function Resolve-SingleThread {
    param([string]$Id)

    $mutation = @"
mutation {
    resolveReviewThread(input: {threadId: "$Id"}) {
        thread {
            id
            isResolved
        }
    }
}
"@

    $result = gh api graphql -f query=$mutation 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Failed to resolve thread ${Id}: $result"
        return $false
    }

    $parsed = $result | ConvertFrom-Json
    if ($parsed.data.resolveReviewThread.thread.isResolved) {
        Write-Host "Resolved thread: $Id" -ForegroundColor Green
        return $true
    } else {
        Write-Warning "Thread $Id may not have been resolved"
        return $false
    }
}

function Get-UnresolvedThreads {
    param([int]$PR)

    # Get repo info
    $repoJson = gh repo view --json owner,name 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to get repo info: $repoJson"
    }
    $repo = $repoJson | ConvertFrom-Json

    $allThreads = @()
    $hasNextPage = $true
    $cursor = $null

    while ($hasNextPage) {
        $cursorArg = if ($cursor) { ", after: \`"$cursor\`"" } else { "" }

        $query = @"
query {
    repository(owner: "$($repo.owner.login)", name: "$($repo.name)") {
        pullRequest(number: $PR) {
            reviewThreads(first: 100$cursorArg) {
                totalCount
                pageInfo {
                    hasNextPage
                    endCursor
                }
                nodes {
                    id
                    isResolved
                    isOutdated
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
"@

        $result = gh api graphql -f query=$query 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to query threads: $result"
        }

        $parsed = $result | ConvertFrom-Json
        $reviewThreads = $parsed.data.repository.pullRequest.reviewThreads
        $allThreads += $reviewThreads.nodes

        $hasNextPage = $reviewThreads.pageInfo.hasNextPage
        $cursor = $reviewThreads.pageInfo.endCursor

        if ($hasNextPage) {
            Write-Verbose "Fetching next page of threads (cursor: $cursor)"
        }
    }

    Write-Verbose "Retrieved $($allThreads.Count) total threads"
    return $allThreads | Where-Object { -not $_.isResolved }
}

# Main execution
if ($PSCmdlet.ParameterSetName -eq 'Single') {
    $success = Resolve-SingleThread -Id $ThreadId
    exit ($success ? 0 : 1)
}
else {
    # Resolve all unresolved threads
    $unresolvedThreads = Get-UnresolvedThreads -PR $PullRequest

    if ($unresolvedThreads.Count -eq 0) {
        Write-Host "All threads on PR #${PullRequest} are already resolved" -ForegroundColor Green
        exit 0
    }

    Write-Host "Found $($unresolvedThreads.Count) unresolved thread(s) on PR #${PullRequest}" -ForegroundColor Cyan

    $resolved = 0
    $failed = 0

    foreach ($thread in $unresolvedThreads) {
        $firstComment = $null
        if ($thread.comments -and $thread.comments.nodes -and $thread.comments.nodes.Count -gt 0) {
            $firstComment = $thread.comments.nodes[0]
        }

        if ($firstComment -and $firstComment.author -and $firstComment.author.login) {
            $author = $firstComment.author.login
        }
        else {
            $author = 'unknown'
        }

        if ($firstComment -and $firstComment.databaseId) {
            $commentId = $firstComment.databaseId
        }
        else {
            $commentId = 'unknown'
        }

        Write-Host "  Resolving thread $($thread.id) (comment $commentId by @$author)..." -ForegroundColor Yellow

        if (Resolve-SingleThread -Id $thread.id) {
            $resolved++
        } else {
            $failed++
        }
    }

    Write-Host ""
    Write-Host "Summary: $resolved resolved, $failed failed" -ForegroundColor (& { if ($failed -eq 0) { 'Green' } else { 'Yellow' } })

    # Return results as JSON for parsing
    [PSCustomObject]@{
        TotalUnresolved = $unresolvedThreads.Count
        Resolved = $resolved
        Failed = $failed
        Success = ($failed -eq 0)
    } | ConvertTo-Json

    exit ($failed -eq 0 ? 0 : 1)
}
