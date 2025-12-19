<#
.SYNOPSIS
    Gets context and metadata for a GitHub Pull Request.

.DESCRIPTION
    Retrieves comprehensive PR information including:
    - Basic metadata (number, title, body, state, author)
    - Branch information (head, base, commits)
    - Labels and reviewers
    - Optionally includes diff or changed files

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER PullRequest
    PR number (required).

.PARAMETER IncludeDiff
    If specified, includes the PR diff (may be large).

.PARAMETER IncludeChangedFiles
    If specified, includes list of changed files.

.PARAMETER DiffStat
    If specified with -IncludeDiff, returns stat format instead of full diff.

.EXAMPLE
    .\Get-PRContext.ps1 -PullRequest 50

.EXAMPLE
    .\Get-PRContext.ps1 -PullRequest 50 -IncludeChangedFiles

.NOTES
    Exit Codes: 0=Success, 1=Invalid params, 2=Not found, 3=API error, 4=Not authenticated
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [int]$PullRequest,
    [switch]$IncludeDiff,
    [switch]$IncludeChangedFiles,
    [switch]$DiffStat
)

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

Write-Verbose "Fetching PR #$PullRequest from $Owner/$Repo"

$jsonFields = "number,title,body,headRefName,baseRefName,state,author,labels,reviewRequests,commits,additions,deletions,changedFiles,mergeable,merged,mergedBy,createdAt,updatedAt"
$prData = gh pr view $PullRequest --repo "$Owner/$Repo" --json $jsonFields 2>&1

if ($LASTEXITCODE -ne 0) {
    if ($prData -match "not found") { Write-ErrorAndExit "PR #$PullRequest not found in $Owner/$Repo" 2 }
    Write-ErrorAndExit "Failed to get PR #$PullRequest: $prData" 3
}

$pr = $prData | ConvertFrom-Json

$output = [PSCustomObject]@{
    Success      = $true
    Number       = $pr.number
    Title        = $pr.title
    Body         = $pr.body
    State        = $pr.state
    Author       = $pr.author.login
    HeadBranch   = $pr.headRefName
    BaseBranch   = $pr.baseRefName
    Labels       = @($pr.labels | ForEach-Object { $_.name })
    Commits      = $pr.commits.totalCount
    Additions    = $pr.additions
    Deletions    = $pr.deletions
    ChangedFiles = $pr.changedFiles
    Mergeable    = $pr.mergeable
    Merged       = $pr.merged
    MergedBy     = if ($pr.mergedBy) { $pr.mergedBy.login } else { $null }
    CreatedAt    = $pr.createdAt
    UpdatedAt    = $pr.updatedAt
    Diff         = $null
    Files        = $null
    Owner        = $Owner
    Repo         = $Repo
}

if ($IncludeDiff) {
    $diff = if ($DiffStat) { gh pr diff $PullRequest --repo "$Owner/$Repo" --stat 2>&1 }
            else { gh pr diff $PullRequest --repo "$Owner/$Repo" 2>&1 }
    if ($LASTEXITCODE -eq 0) { $output.Diff = $diff -join "`n" }
}

if ($IncludeChangedFiles) {
    $files = gh pr diff $PullRequest --repo "$Owner/$Repo" --name-only 2>&1
    if ($LASTEXITCODE -eq 0) { $output.Files = @($files | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) }
}

Write-Output $output
Write-Host "PR #$($output.Number): $($output.Title)" -ForegroundColor Cyan
Write-Host "  Branch: $($output.HeadBranch) -> $($output.BaseBranch) | State: $($output.State)" -ForegroundColor Gray
