<#
.SYNOPSIS
    Gets all review comments for a GitHub Pull Request with pagination.

.DESCRIPTION
    Retrieves PR review comments (code-level) with full pagination support.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER PullRequest
    PR number (required).

.PARAMETER Author
    Optional filter by author login name.

.PARAMETER IncludeDiffHunk
    If specified, includes the diff context for each comment.

.EXAMPLE
    .\Get-PRReviewComments.ps1 -PullRequest 50
    .\Get-PRReviewComments.ps1 -PullRequest 50 -Author "cursor[bot]"

.NOTES
    Exit Codes: 0=Success, 1=Invalid params, 2=Not found, 3=API error, 4=Not authenticated
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [int]$PullRequest,
    [string]$Author,
    [switch]$IncludeDiffHunk
)

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

Write-Verbose "Fetching review comments for PR #$PullRequest"

$allComments = Invoke-GhApiPaginated -Endpoint "repos/$Owner/$Repo/pulls/$PullRequest/comments"

$processedComments = foreach ($comment in $allComments) {
    if ($Author -and $comment.user.login -ne $Author) { continue }

    [PSCustomObject]@{
        Id          = $comment.id
        Author      = $comment.user.login
        AuthorType  = $comment.user.type
        Path        = $comment.path
        Line        = if ($comment.line) { $comment.line } else { $comment.original_line }
        Side        = $comment.side
        Body        = $comment.body
        CreatedAt   = $comment.created_at
        UpdatedAt   = $comment.updated_at
        InReplyToId = $comment.in_reply_to_id
        IsReply     = $null -ne $comment.in_reply_to_id
        DiffHunk    = if ($IncludeDiffHunk) { $comment.diff_hunk } else { $null }
        HtmlUrl     = $comment.html_url
        CommitId    = $comment.commit_id
    }
}

$authorGroups = @($processedComments) | Group-Object -Property Author

$output = [PSCustomObject]@{
    Success       = $true
    PullRequest   = $PullRequest
    Owner         = $Owner
    Repo          = $Repo
    TotalComments = @($processedComments).Count
    TopLevelCount = (@($processedComments) | Where-Object { -not $_.IsReply }).Count
    ReplyCount    = (@($processedComments) | Where-Object { $_.IsReply }).Count
    AuthorSummary = @($authorGroups | ForEach-Object { [PSCustomObject]@{ Author = $_.Name; Count = $_.Count } })
    Comments      = @($processedComments)
}

Write-Output $output
Write-Host "PR #$PullRequest: $($output.TotalComments) review comments" -ForegroundColor Cyan
