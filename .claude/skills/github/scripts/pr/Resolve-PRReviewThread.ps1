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

.NOTES
    EXIT CODES:
    0  - Success: Thread(s) resolved successfully

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

function Resolve-ReviewThread {
    param([string]$Id)

    # Uses GraphQL variables for security (prevents injection via ThreadId)
    # Use GraphQL variables to prevent injection (ADR-015 compliant)
    $mutation = @'
mutation($threadId: ID!) {
    resolveReviewThread(input: {threadId: $threadId}) {
        thread {
            id
            isResolved
        }
    }
}
'@

    $result = gh api graphql -f query=$mutation -f threadId="$Id" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Failed to resolve thread ${Id}: $result"
        return $false
    }

    try {
        $parsed = $result | ConvertFrom-Json
        if ($parsed.data.resolveReviewThread.thread.isResolved) {
            Write-Host "Resolved thread: $Id" -ForegroundColor Green
            return $true
        } else {
            Write-Warning "Thread $Id may not have been resolved. Response: $result"
            return $false
        }
    }
    catch {
        Write-Warning "Failed to parse GraphQL response for thread $Id. Raw response: $result"
        return $false
    }
}

function Get-UnresolvedReviewThreads {
    param([int]$PR)

    # Get repo info
    $repoJson = gh repo view --json owner,name 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to get repo info: $repoJson"
    }
    $repo = $repoJson | ConvertFrom-Json

    # Uses GraphQL variables for security (prevents injection via owner/name/PR)
    # Use GraphQL variables to prevent injection (ADR-015 compliant)
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

    return $threads | Where-Object { -not $_.isResolved }
}

# Main execution
if ($PSCmdlet.ParameterSetName -eq 'Single') {
    $success = Resolve-ReviewThread -Id $ThreadId
    exit ($success ? 0 : 1)
}
else {
    # Resolve all unresolved threads
    $unresolvedThreads = Get-UnresolvedReviewThreads -PR $PullRequest

    if (-not $unresolvedThreads) {
        Write-Host "All threads on PR #${PullRequest} are already resolved" -ForegroundColor Green
        exit 0
    }

    Write-Host "Found $($unresolvedThreads.Count) unresolved thread(s) on PR #${PullRequest}" -ForegroundColor Cyan

    $resolved = 0
    $failed = 0

    foreach ($thread in $unresolvedThreads) {
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

        Write-Host "  Resolving thread $($thread.id) (comment $commentId by @$author)..." -ForegroundColor Yellow

        if (Resolve-ReviewThread -Id $thread.id) {
            $resolved++
        } else {
            $failed++
        }
    }

    Write-Host ""
    Write-Host "Summary: $resolved resolved, $failed failed" -ForegroundColor $(if ($failed -eq 0) { 'Green' } else { 'Yellow' })

    # Return results as JSON for parsing
    [PSCustomObject]@{
        TotalUnresolved = $unresolvedThreads.Count
        Resolved = $resolved
        Failed = $failed
        Success = ($failed -eq 0)
    } | ConvertTo-Json

    exit ($failed -eq 0 ? 0 : 1)
}
