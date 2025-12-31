<#
.SYNOPSIS
    Gets a single PR review thread by its GraphQL ID.

.DESCRIPTION
    Retrieves detailed information about a specific review thread using its
    GraphQL node ID (e.g., PRRT_kwDOQoWRls5m7ln8).

    Use this when you have a thread ID from previous operations and need
    full thread details including all comments.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER ThreadId
    The GraphQL node ID of the review thread (required).
    Format: PRRT_... (Pull Request Review Thread)

.EXAMPLE
    ./Get-ThreadById.ps1 -ThreadId "PRRT_kwDOQoWRls5m7ln8"

.EXAMPLE
    ./Get-ThreadById.ps1 -Owner "myorg" -Repo "myrepo" -ThreadId "PRRT_abc123"

.NOTES
    Exit Codes:
        0 - Success
        1 - Invalid parameters
        2 - Thread not found
        3 - API error
        4 - Not authenticated

    Uses GraphQL node query for direct thread lookup.
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)]
    [string]$ThreadId
)

$ErrorActionPreference = 'Stop'

# Import shared helpers
Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubCore.psm1") -Force

#region Validation

# Parameter validation first (before external checks per Skill-Testing-Exit-Code-Order-001)
if ([string]::IsNullOrWhiteSpace($ThreadId)) {
    Write-ErrorAndExit "ThreadId parameter is required." 1
}

# Validate ThreadId format (should start with PRRT_ for review threads)
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

Write-Verbose "Fetching thread $ThreadId from $Owner/$Repo"

#endregion

#region GraphQL Query

# Uses GraphQL variables for security (prevents injection via ThreadId)
$query = @'
query($threadId: ID!) {
    node(id: $threadId) {
        ... on PullRequestReviewThread {
            id
            isResolved
            isOutdated
            path
            line
            startLine
            diffSide
            comments(first: 100) {
                totalCount
                nodes {
                    id
                    databaseId
                    body
                    author { login }
                    createdAt
                    updatedAt
                    isMinimized
                    minimizedReason
                }
            }
        }
    }
}
'@

$result = gh api graphql -f query=$query -f threadId="$ThreadId" 2>&1
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

#endregion

#region Process Response

$thread = $parsed.data.node

if ($null -eq $thread -or $null -eq $thread.id) {
    Write-ErrorAndExit "Thread $ThreadId not found or is not a review thread." 2
}

# Transform comments to consistent format
$comments = @()
if ($thread.comments -and $thread.comments.nodes) {
    $comments = $thread.comments.nodes | ForEach-Object {
        [PSCustomObject]@{
            Id = $_.databaseId
            NodeId = $_.id
            Author = if ($_.author) { $_.author.login } else { $null }
            Body = $_.body
            CreatedAt = $_.createdAt
            UpdatedAt = $_.updatedAt
            IsMinimized = $_.isMinimized
            MinimizedReason = $_.minimizedReason
        }
    }
}

# Build output
$output = [PSCustomObject]@{
    Success = $true
    ThreadId = $thread.id
    IsResolved = $thread.isResolved
    IsOutdated = $thread.isOutdated
    Path = $thread.path
    Line = $thread.line
    StartLine = $thread.startLine
    DiffSide = $thread.diffSide
    CommentCount = $thread.comments.totalCount
    Comments = @($comments)
}

#endregion

#region Output

Write-Host "Thread ${ThreadId}:" -ForegroundColor Cyan
$status = if ($thread.isResolved) { "Resolved" } else { "Unresolved" }
$outdated = if ($thread.isOutdated) { " (Outdated)" } else { "" }
Write-Host "  Status: $status$outdated" -ForegroundColor $(if ($thread.isResolved) { 'Green' } else { 'Yellow' })
Write-Host "  Path: $($thread.path)" -ForegroundColor Gray
Write-Host "  Line: $($thread.line)" -ForegroundColor Gray
Write-Host "  Comments: $($thread.comments.totalCount)" -ForegroundColor Gray

$output | ConvertTo-Json -Depth 10

#endregion
