<#
.SYNOPSIS
    Adds a reply to a GitHub PR review thread using GraphQL.

.DESCRIPTION
    Posts a reply to a review thread using the thread ID (PRRT_...) rather than
    comment ID. This is required for proper thread management when using
    branch protection rules.

    Optionally resolves the thread after posting the reply.

.PARAMETER ThreadId
    The GraphQL thread ID (e.g., PRRT_kwDOQoWRls5m3L76).

.PARAMETER Body
    Reply text (inline). Mutually exclusive with BodyFile.

.PARAMETER BodyFile
    Path to file containing reply. Mutually exclusive with Body.

.PARAMETER Resolve
    If specified, resolves the thread after posting the reply.

.EXAMPLE
    ./Add-PRReviewThreadReply.ps1 -ThreadId "PRRT_kwDOQoWRls5m3L76" -Body "Fixed in abc1234."

.EXAMPLE
    ./Add-PRReviewThreadReply.ps1 -ThreadId "PRRT_kwDOQoWRls5m3L76" -Body "Fixed." -Resolve

.EXAMPLE
    ./Add-PRReviewThreadReply.ps1 -ThreadId "PRRT_kwDOQoWRls5m3L76" -BodyFile ./response.md

.NOTES
    Exit Codes: 0=Success, 1=Invalid params, 2=File not found, 3=API error, 4=Not authenticated

    Uses GraphQL API as the REST API does not support thread-based replies.
    Thread IDs can be obtained from Get-PRReviewThreads.ps1.
#>

[CmdletBinding(DefaultParameterSetName = 'BodyText')]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^PRRT_')]
    [string]$ThreadId,

    [Parameter(ParameterSetName = 'BodyText', Mandatory)]
    [string]$Body,

    [Parameter(ParameterSetName = 'BodyFile', Mandatory)]
    [string]$BodyFile,

    [switch]$Resolve
)

$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

Assert-GhAuthenticated

# Resolve body content
if ($BodyFile) {
    Assert-ValidBodyFile -BodyFile $BodyFile
    $Body = Get-Content -Path $BodyFile -Raw -Encoding UTF8
}

if ([string]::IsNullOrWhiteSpace($Body)) {
    Write-ErrorAndExit "Body cannot be empty." 1
}

Write-Verbose "Posting reply to thread $ThreadId"

# GraphQL mutation to add reply to review thread
# Uses GraphQL variables for security (prevents injection via ThreadId/Body)
$mutation = @'
mutation($threadId: ID!, $body: String!) {
    addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $threadId, body: $body}) {
        comment {
            id
            databaseId
            url
            createdAt
            author {
                login
            }
        }
    }
}
'@

$result = gh api graphql -f query=$mutation -f threadId="$ThreadId" -f body="$Body" 2>&1
if ($LASTEXITCODE -ne 0) {
    if ($result -match "Could not resolve") {
        Write-ErrorAndExit "Thread $ThreadId not found" 2
    }
    Write-ErrorAndExit "Failed to post thread reply: $result" 3
}

try {
    $parsed = $result | ConvertFrom-Json
}
catch {
    Write-ErrorAndExit "Failed to parse GraphQL response: $result" 3
}

$comment = $parsed.data.addPullRequestReviewThreadReply.comment

if ($null -eq $comment) {
    Write-ErrorAndExit "Reply may not have been posted. Response: $result" 3
}

# Optionally resolve the thread
$threadResolved = $false
if ($Resolve) {
    Write-Verbose "Resolving thread $ThreadId"

    $resolveMutation = @'
mutation($threadId: ID!) {
    resolveReviewThread(input: {threadId: $threadId}) {
        thread {
            id
            isResolved
        }
    }
}
'@

    $resolveResult = gh api graphql -f query=$resolveMutation -f threadId="$ThreadId" 2>&1
    if ($LASTEXITCODE -eq 0) {
        try {
            $resolvedParsed = $resolveResult | ConvertFrom-Json
            $threadResolved = $resolvedParsed.data.resolveReviewThread.thread.isResolved
        }
        catch {
            Write-Warning "Thread reply posted but resolution status unclear: $resolveResult"
        }
    }
    else {
        Write-Warning "Thread reply posted but failed to resolve: $resolveResult"
    }
}

# Output result
$output = [PSCustomObject]@{
    Success        = $true
    ThreadId       = $ThreadId
    CommentId      = $comment.databaseId
    CommentNodeId  = $comment.id
    HtmlUrl        = $comment.url
    CreatedAt      = $comment.createdAt
    Author         = if ($comment.author) { $comment.author.login } else { $null }
    ThreadResolved = $threadResolved
}

$output | ConvertTo-Json -Depth 5

Write-Host "Posted reply to thread $ThreadId" -ForegroundColor Green
Write-Host "  Comment ID: $($output.CommentId)" -ForegroundColor Gray
Write-Host "  URL: $($output.HtmlUrl)" -ForegroundColor Cyan
if ($Resolve) {
    $resolveStatus = if ($threadResolved) { "Yes" } else { "Failed" }
    Write-Host "  Resolved: $resolveStatus" -ForegroundColor $(if ($threadResolved) { 'Green' } else { 'Yellow' })
}
