<#
.SYNOPSIS
    Gets all review threads for a GitHub Pull Request.

.DESCRIPTION
    Retrieves review threads with their resolution status, comments,
    and thread IDs needed for Resolve-PRReviewThread.ps1.

    This script complements Get-PRReviewComments by providing thread-level
    context rather than flat comment lists.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER PullRequest
    PR number (required).

.PARAMETER UnresolvedOnly
    If specified, returns only unresolved threads.

.PARAMETER IncludeComments
    If specified, includes all comments in each thread (not just first).

.EXAMPLE
    .\Get-PRReviewThreads.ps1 -PullRequest 50

.EXAMPLE
    .\Get-PRReviewThreads.ps1 -PullRequest 50 -UnresolvedOnly

.NOTES
    Exit Codes: 0=Success, 1=Invalid params, 2=Not found, 3=API error, 4=Not authenticated

    Uses GraphQL API for thread data (REST API doesn't expose thread structure).
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [int]$PullRequest,
    [switch]$UnresolvedOnly,
    [switch]$IncludeComments
)

$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

Write-Verbose "Fetching review threads for PR #$PullRequest in $Owner/$Repo"

# GraphQL query to get review threads
$commentsLimit = & { if ($IncludeComments) { 50 } else { 1 } }

$query = @"
query {
    repository(owner: "$Owner", name: "$Repo") {
        pullRequest(number: $PullRequest) {
            reviewThreads(first: 100) {
                totalCount
                nodes {
                    id
                    isResolved
                    isOutdated
                    path
                    line
                    startLine
                    diffSide
                    comments(first: $commentsLimit) {
                        totalCount
                        nodes {
                            id
                            databaseId
                            body
                            author { login }
                            createdAt
                            updatedAt
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
    if ($result -match "Could not resolve") {
        Write-ErrorAndExit "PR #$PullRequest not found in $Owner/$Repo" 2
    }
    Write-ErrorAndExit "Failed to query review threads: $result" 3
}

try {
    $parsed = $result | ConvertFrom-Json
}
catch {
    Write-ErrorAndExit "Failed to parse GraphQL response: $result" 3
}

$threads = $parsed.data.repository.pullRequest.reviewThreads.nodes

if ($null -eq $threads) {
    Write-ErrorAndExit "PR #$PullRequest not found or has no review threads" 2
}

# Filter if requested
if ($UnresolvedOnly) {
    $threads = $threads | Where-Object { -not $_.isResolved }
}

# Transform to output format
$output = $threads | ForEach-Object {
    $thread = $_
    $firstComment = if ($thread.comments.nodes.Count -gt 0) { $thread.comments.nodes[0] } else { $null }

    [PSCustomObject]@{
        ThreadId = $thread.id
        IsResolved = $thread.isResolved
        IsOutdated = $thread.isOutdated
        Path = $thread.path
        Line = $thread.line
        StartLine = $thread.startLine
        DiffSide = $thread.diffSide
        CommentCount = $thread.comments.totalCount
        FirstCommentId = if ($firstComment) { $firstComment.databaseId } else { $null }
        FirstCommentAuthor = if ($firstComment -and $firstComment.author) { $firstComment.author.login } else { $null }
        FirstCommentBody = if ($firstComment) { $firstComment.body } else { $null }
        FirstCommentCreatedAt = if ($firstComment) { $firstComment.createdAt } else { $null }
        Comments = if ($IncludeComments) {
            $thread.comments.nodes | ForEach-Object {
                [PSCustomObject]@{
                    Id = $_.databaseId
                    Author = if ($_.author) { $_.author.login } else { $null }
                    Body = $_.body
                    CreatedAt = $_.createdAt
                }
            }
        } else { $null }
    }
}

# Summary output
$totalCount = @($threads).Count
$unresolvedCount = @($threads | Where-Object { -not $_.isResolved }).Count
$resolvedCount = $totalCount - $unresolvedCount

Write-Host "PR #$PullRequest Review Threads:" -ForegroundColor Cyan
Write-Host "  Total: $totalCount | Resolved: $resolvedCount | Unresolved: $unresolvedCount" -ForegroundColor Gray

# Return structured output
[PSCustomObject]@{
    Success = $true
    PullRequest = $PullRequest
    Owner = $Owner
    Repo = $Repo
    TotalThreads = $totalCount
    ResolvedCount = $resolvedCount
    UnresolvedCount = $unresolvedCount
    Threads = @($output)
} | ConvertTo-Json -Depth 10
