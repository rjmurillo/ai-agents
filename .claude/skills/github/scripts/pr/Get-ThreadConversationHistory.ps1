<#
.SYNOPSIS
    Gets the full conversation history of a PR review thread.

.DESCRIPTION
    Retrieves all comments in a review thread with detailed metadata.
    Unlike Get-ThreadById which returns up to 100 comments, this script
    supports pagination for threads with many comments.

    The output includes comment order, author info, timestamps, and
    whether comments have been minimized (hidden).

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER ThreadId
    The GraphQL node ID of the review thread (required).
    Format: PRRT_... (Pull Request Review Thread)

.PARAMETER IncludeMinimized
    If specified, includes minimized (hidden) comments in output.
    By default, minimized comments are excluded.

.EXAMPLE
    ./Get-ThreadConversationHistory.ps1 -ThreadId "PRRT_kwDOQoWRls5m7ln8"

.EXAMPLE
    ./Get-ThreadConversationHistory.ps1 -ThreadId "PRRT_abc123" -IncludeMinimized

.NOTES
    Exit Codes:
        0 - Success
        1 - Invalid parameters
        2 - Thread not found
        3 - API error
        4 - Not authenticated

    Uses GraphQL with pagination support for threads with 100+ comments.
    
    See: ADR-035 Exit Code Standardization
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)]
    [string]$ThreadId,
    [switch]$IncludeMinimized
)

$ErrorActionPreference = 'Stop'

# Import shared helpers
Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubCore.psm1") -Force

#region Validation

# Parameter validation first (before external checks per Skill-Testing-Exit-Code-Order-001)
if ([string]::IsNullOrWhiteSpace($ThreadId)) {
    Write-ErrorAndExit "ThreadId parameter is required." 1
}

if (-not ($ThreadId -match '^PRRT_')) {
    Write-ErrorAndExit "Invalid ThreadId format. Expected PRRT_... format." 1
}

# External tool check
Assert-GhAuthenticated

#endregion

#region Resolve Repository

$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

Write-Verbose "Fetching conversation history for thread $ThreadId"

#endregion

#region Fetch Comments with Pagination

# GraphQL query for thread with paginated comments
# Uses variables for security (prevents injection)
$query = @'
query($threadId: ID!, $first: Int!, $after: String) {
    node(id: $threadId) {
        ... on PullRequestReviewThread {
            id
            isResolved
            isOutdated
            path
            line
            startLine
            diffSide
            comments(first: $first, after: $after) {
                totalCount
                pageInfo {
                    hasNextPage
                    endCursor
                }
                nodes {
                    id
                    databaseId
                    body
                    author { login }
                    createdAt
                    updatedAt
                    isMinimized
                    minimizedReason
                    replyTo { databaseId }
                }
            }
        }
    }
}
'@

$allComments = [System.Collections.Generic.List[object]]::new()
$pageSize = 100
$cursor = $null
$threadInfo = $null

do {
    # Build command - note: using splatting would be cleaner but gh api doesn't support it well
    if ($cursor) {
        $result = gh api graphql -f query=$query -f threadId="$ThreadId" -F first=$pageSize -f after="$cursor" 2>&1
    } else {
        $result = gh api graphql -f query=$query -f threadId="$ThreadId" -F first=$pageSize 2>&1
    }

    if ($LASTEXITCODE -ne 0) {
        if ($result -match "Could not resolve" -or $result -match "not found") {
            Write-ErrorAndExit "Thread $ThreadId not found." 2
        }
        Write-ErrorAndExit "Failed to query thread: $result" 3
    }

    try {
        $parsed = $result | ConvertFrom-Json
    }
    catch {
        Write-ErrorAndExit "Failed to parse GraphQL response: $result" 3
    }

    $node = $parsed.data.node

    if ($null -eq $node -or $null -eq $node.id) {
        Write-ErrorAndExit "Thread $ThreadId not found or is not a review thread." 2
    }

    # Store thread info from first page
    if ($null -eq $threadInfo) {
        $threadInfo = [PSCustomObject]@{
            ThreadId = $node.id
            IsResolved = $node.isResolved
            IsOutdated = $node.isOutdated
            Path = $node.path
            Line = $node.line
            StartLine = $node.startLine
            DiffSide = $node.diffSide
            TotalComments = $node.comments.totalCount
        }
    }

    # Add comments from this page
    foreach ($comment in $node.comments.nodes) {
        $allComments.Add($comment)
    }

    # Check for more pages
    $hasNextPage = $node.comments.pageInfo.hasNextPage
    $cursor = $node.comments.pageInfo.endCursor

} while ($hasNextPage)

#endregion

#region Process Comments

# Filter out minimized comments unless requested
$filteredComments = $allComments
if (-not $IncludeMinimized) {
    $filteredComments = $allComments | Where-Object { -not $_.isMinimized }
}

# Transform to output format with sequence numbers
$outputComments = @()
$sequence = 0
foreach ($comment in $filteredComments) {
    $sequence++
    $outputComments += [PSCustomObject]@{
        Sequence = $sequence
        Id = $comment.databaseId
        NodeId = $comment.id
        Author = if ($comment.author) { $comment.author.login } else { $null }
        Body = $comment.body
        CreatedAt = $comment.createdAt
        UpdatedAt = $comment.updatedAt
        IsMinimized = $comment.isMinimized
        MinimizedReason = $comment.minimizedReason
        ReplyToId = if ($comment.replyTo) { $comment.replyTo.databaseId } else { $null }
    }
}

#endregion

#region Output

Write-Host "Thread Conversation: $ThreadId" -ForegroundColor Cyan
$status = if ($threadInfo.IsResolved) { "Resolved" } else { "Unresolved" }
$outdated = if ($threadInfo.IsOutdated) { " (Outdated)" } else { "" }
Write-Host "  Status: $status$outdated" -ForegroundColor $(if ($threadInfo.IsResolved) { 'Green' } else { 'Yellow' })
Write-Host "  Path: $($threadInfo.Path)" -ForegroundColor Gray
Write-Host "  Line: $($threadInfo.Line)" -ForegroundColor Gray
Write-Host "  Total Comments: $($threadInfo.TotalComments)" -ForegroundColor Gray

if (-not $IncludeMinimized) {
    $minimizedCount = $allComments.Count - $outputComments.Count
    if ($minimizedCount -gt 0) {
        Write-Host "  Hidden (minimized): $minimizedCount (use -IncludeMinimized to show)" -ForegroundColor DarkGray
    }
}

# Brief conversation preview
Write-Host ""
Write-Host "Conversation:" -ForegroundColor Cyan
foreach ($c in $outputComments | Select-Object -First 5) {
    $preview = if ($c.Body.Length -gt 60) { $c.Body.Substring(0, 60) + "..." } else { $c.Body }
    $preview = $preview -replace "`n", " " -replace "`r", ""
    Write-Host "  [$($c.Sequence)] @$($c.Author): $preview" -ForegroundColor Gray
}
if ($outputComments.Count -gt 5) {
    Write-Host "  ... and $($outputComments.Count - 5) more comment(s)" -ForegroundColor DarkGray
}

# Structured output
$output = [PSCustomObject]@{
    Success = $true
    ThreadId = $threadInfo.ThreadId
    IsResolved = $threadInfo.IsResolved
    IsOutdated = $threadInfo.IsOutdated
    Path = $threadInfo.Path
    Line = $threadInfo.Line
    StartLine = $threadInfo.StartLine
    DiffSide = $threadInfo.DiffSide
    TotalComments = $threadInfo.TotalComments
    ReturnedComments = $outputComments.Count
    MinimizedExcluded = if (-not $IncludeMinimized) { $allComments.Count - $outputComments.Count } else { 0 }
    Comments = @($outputComments)
}

$output | ConvertTo-Json -Depth 10

#endregion
