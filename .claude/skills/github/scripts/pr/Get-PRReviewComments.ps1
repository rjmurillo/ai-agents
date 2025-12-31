<#
.SYNOPSIS
    Gets all comments for a GitHub Pull Request with pagination.

.DESCRIPTION
    Retrieves PR review comments (code-level) and optionally issue comments (PR-level)
    with full pagination support.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER PullRequest
    PR number (required).

.PARAMETER Author
    Optional filter by author login name.

.PARAMETER IncludeDiffHunk
    If specified, includes the diff context for each review comment.

.PARAMETER IncludeIssueComments
    If specified, also fetches issue comments (top-level PR comments like AI Quality Gate).
    These are comments posted via /issues/{n}/comments API, not code-level review comments.

.EXAMPLE
    .\Get-PRReviewComments.ps1 -PullRequest 50
    .\Get-PRReviewComments.ps1 -PullRequest 50 -IncludeIssueComments
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
    [switch]$IncludeDiffHunk,
    [switch]$IncludeIssueComments
)

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubCore.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

Write-Verbose "Fetching review comments for PR #$PullRequest"

# Fetch review comments (code-level comments on specific lines/files)
$reviewComments = Invoke-GhApiPaginated -Endpoint "repos/$Owner/$Repo/pulls/$PullRequest/comments"

$processedReviewComments = @(foreach ($comment in $reviewComments) {
    if ($Author -and $comment.user.login -ne $Author) { continue }

    [PSCustomObject]@{
        Id          = $comment.id
        CommentType = "Review"
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
})

# Fetch issue comments (top-level PR comments) if requested
$processedIssueComments = @()
if ($IncludeIssueComments) {
    Write-Verbose "Fetching issue comments for PR #$PullRequest"
    $issueComments = Invoke-GhApiPaginated -Endpoint "repos/$Owner/$Repo/issues/$PullRequest/comments"

    $processedIssueComments = @(foreach ($comment in $issueComments) {
        if ($Author -and $comment.user.login -ne $Author) { continue }

        [PSCustomObject]@{
            Id          = $comment.id
            CommentType = "Issue"
            Author      = $comment.user.login
            AuthorType  = $comment.user.type
            Path        = $null  # Issue comments are not on specific files
            Line        = $null  # Issue comments are not on specific lines
            Side        = $null
            Body        = $comment.body
            CreatedAt   = $comment.created_at
            UpdatedAt   = $comment.updated_at
            InReplyToId = $null  # Issue comments don't have reply threading like review comments
            IsReply     = $false
            DiffHunk    = $null
            HtmlUrl     = $comment.html_url
            CommitId    = $null
        }
    })
}

# Combine all comments
$allProcessedComments = @($processedReviewComments) + @($processedIssueComments)

# Sort by creation date
$allProcessedComments = $allProcessedComments | Sort-Object -Property CreatedAt

$authorGroups = @($allProcessedComments) | Group-Object -Property Author

$reviewCount = @($processedReviewComments).Count
$issueCount = @($processedIssueComments).Count

$output = [PSCustomObject]@{
    Success            = $true
    PullRequest        = $PullRequest
    Owner              = $Owner
    Repo               = $Repo
    TotalComments      = @($allProcessedComments).Count
    ReviewCommentCount = $reviewCount
    IssueCommentCount  = $issueCount
    TopLevelCount      = (@($allProcessedComments) | Where-Object { -not $_.IsReply }).Count
    ReplyCount         = (@($allProcessedComments) | Where-Object { $_.IsReply }).Count
    AuthorSummary      = @($authorGroups | ForEach-Object { [PSCustomObject]@{ Author = $_.Name; Count = $_.Count } })
    Comments           = @($allProcessedComments)
}

Write-Output $output

$reviewText = if ($reviewCount -eq 1) { "review comment" } else { "review comments" }
$commentSummary = "PR #$($PullRequest): $reviewCount $reviewText"
if ($IncludeIssueComments) {
    $issueText = if ($issueCount -eq 1) { "issue comment" } else { "issue comments" }
    $commentSummary += " + $issueCount $issueText"
}
Write-Host $commentSummary -ForegroundColor Cyan
