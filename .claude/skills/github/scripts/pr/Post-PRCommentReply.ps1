<#
.SYNOPSIS
    Posts a reply to a GitHub PR review comment or top-level PR comment.

.DESCRIPTION
    Posts replies using the correct endpoint for thread preservation:
    - Review comments: Uses in_reply_to for thread context (Skill-PR-004)
    - Issue comments: Posts to issue comments endpoint for top-level

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER PullRequest
    PR number (required).

.PARAMETER CommentId
    Review comment ID to reply to. Omit for top-level comment.

.PARAMETER Body
    Reply text (inline). Mutually exclusive with BodyFile.

.PARAMETER BodyFile
    Path to file containing reply. Mutually exclusive with Body.

.EXAMPLE
    .\Post-PRCommentReply.ps1 -PullRequest 50 -CommentId 123456 -Body "Fixed in abc1234."
    .\Post-PRCommentReply.ps1 -PullRequest 50 -Body "All comments addressed."

.NOTES
    Exit Codes: 0=Success, 1=Invalid params, 2=File not found, 3=API error, 4=Not authenticated
    
    See: ADR-035 Exit Code Standardization
#>

[CmdletBinding(DefaultParameterSetName = 'BodyText')]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [int]$PullRequest,
    [long]$CommentId,
    [Parameter(ParameterSetName = 'BodyText', Mandatory)] [string]$Body,
    [Parameter(ParameterSetName = 'BodyFile', Mandatory)] [string]$BodyFile
)

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubCore.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

# Resolve body content
if ($BodyFile) {
    if (-not (Test-Path $BodyFile)) { Write-ErrorAndExit "Body file not found: $BodyFile" 2 }
    $Body = Get-Content -Path $BodyFile -Raw -Encoding UTF8
}

if ([string]::IsNullOrWhiteSpace($Body)) { Write-ErrorAndExit "Body cannot be empty." 1 }

# Post reply using the appropriate endpoint per GitHub REST API docs
# See: https://docs.github.com/en/rest/pulls/comments#create-a-reply-for-a-review-comment
if ($CommentId) {
    Write-Verbose "Posting in-thread reply to comment $CommentId"
    # Use dedicated /replies endpoint for cleaner thread replies
    $result = gh api "repos/$Owner/$Repo/pulls/$PullRequest/comments/$CommentId/replies" -X POST -f body=$Body 2>&1
}
else {
    Write-Verbose "Posting top-level PR comment"
    # Top-level PR comments use the issues API (PRs are a type of issue)
    $result = gh api "repos/$Owner/$Repo/issues/$PullRequest/comments" -X POST -f body=$Body 2>&1
}

if ($LASTEXITCODE -ne 0) { Write-ErrorAndExit "Failed to post comment: $result" 3 }

$response = $result | ConvertFrom-Json

$output = [PSCustomObject]@{
    Success     = $true
    CommentId   = $response.id
    HtmlUrl     = $response.html_url
    PullRequest = $PullRequest
    InReplyTo   = $CommentId
    CreatedAt   = $response.created_at
}

Write-Output $output
Write-Host "Posted reply to PR #$PullRequest" -ForegroundColor Green
Write-Host "  URL: $($output.HtmlUrl)" -ForegroundColor Cyan
