<#
.SYNOPSIS
    Gets unique reviewers for a GitHub Pull Request.

.DESCRIPTION
    Enumerates all unique reviewers from review comments, issue comments,
    requested reviewers, and submitted reviews. Critical for avoiding
    "single-bot blindness" per Skill-PR-001.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER PullRequest
    PR number (required).

.PARAMETER ExcludeBots
    If specified, excludes bot accounts.

.PARAMETER ExcludeAuthor
    If specified, excludes the PR author.

.EXAMPLE
    .\Get-PRReviewers.ps1 -PullRequest 50
    .\Get-PRReviewers.ps1 -PullRequest 50 -ExcludeBots

.NOTES
    Exit Codes: 0=Success, 1=Invalid params, 2=Not found, 3=API error, 4=Not authenticated
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [int]$PullRequest,
    [switch]$ExcludeBots,
    [switch]$ExcludeAuthor
)

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

# Get PR author
$prData = gh pr view $PullRequest --repo "$Owner/$Repo" --json author,reviewRequests,reviews 2>&1
if ($LASTEXITCODE -ne 0) {
    if ($prData -match "not found") { Write-ErrorAndExit "PR #$PullRequest not found" 2 }
    Write-ErrorAndExit "Failed to get PR: $prData" 3
}

$pr = $prData | ConvertFrom-Json
$prAuthor = $pr.author.login

$reviewerMap = @{}

# Review comments
$reviewComments = Invoke-GhApiPaginated -Endpoint "repos/$Owner/$Repo/pulls/$PullRequest/comments"
foreach ($c in $reviewComments) {
    $login = $c.user.login
    if (-not $reviewerMap.ContainsKey($login)) {
        $reviewerMap[$login] = @{ Login = $login; Type = $c.user.type; IsBot = $c.user.type -eq "Bot" -or $login -match '\[bot\]$'; ReviewComments = 0; IssueComments = 0 }
    }
    $reviewerMap[$login].ReviewComments++
}

# Issue comments
$issueComments = Invoke-GhApiPaginated -Endpoint "repos/$Owner/$Repo/issues/$PullRequest/comments"
foreach ($c in $issueComments) {
    $login = $c.user.login
    if (-not $reviewerMap.ContainsKey($login)) {
        $reviewerMap[$login] = @{ Login = $login; Type = $c.user.type; IsBot = $c.user.type -eq "Bot" -or $login -match '\[bot\]$'; ReviewComments = 0; IssueComments = 0 }
    }
    $reviewerMap[$login].IssueComments++
}

# Requested + submitted reviews
foreach ($r in $pr.reviewRequests) { if ($r.login -and -not $reviewerMap.ContainsKey($r.login)) { $reviewerMap[$r.login] = @{ Login = $r.login; Type = "User"; IsBot = $false; ReviewComments = 0; IssueComments = 0 } } }
foreach ($r in $pr.reviews) { if ($r.author.login -and -not $reviewerMap.ContainsKey($r.author.login)) { $reviewerMap[$r.author.login] = @{ Login = $r.author.login; Type = "User"; IsBot = $r.author.login -match '\[bot\]$'; ReviewComments = 0; IssueComments = 0 } } }

$reviewers = $reviewerMap.Values | ForEach-Object {
    [PSCustomObject]@{ Login = $_.Login; Type = $_.Type; IsBot = $_.IsBot; ReviewComments = $_.ReviewComments; IssueComments = $_.IssueComments; TotalComments = $_.ReviewComments + $_.IssueComments }
}

if ($ExcludeBots) { $reviewers = $reviewers | Where-Object { -not $_.IsBot } }
if ($ExcludeAuthor) { $reviewers = $reviewers | Where-Object { $_.Login -ne $prAuthor } }

$reviewers = @($reviewers | Sort-Object -Property TotalComments -Descending)

$output = [PSCustomObject]@{
    Success        = $true
    PullRequest    = $PullRequest
    PRAuthor       = $prAuthor
    TotalReviewers = $reviewers.Count
    BotCount       = ($reviewers | Where-Object { $_.IsBot }).Count
    HumanCount     = ($reviewers | Where-Object { -not $_.IsBot }).Count
    Reviewers      = $reviewers
}

Write-Output $output
Write-Host "PR #$PullRequest: $($output.TotalReviewers) reviewers (Humans: $($output.HumanCount), Bots: $($output.BotCount))" -ForegroundColor Cyan
