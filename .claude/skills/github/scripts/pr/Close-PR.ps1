<#
.SYNOPSIS
    Closes a GitHub Pull Request.

.DESCRIPTION
    Closes a PR with optional comment explaining the reason.
    Supports idempotency - returns success if already closed.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER PullRequest
    PR number (required).

.PARAMETER Comment
    Optional comment to post before closing.

.PARAMETER CommentFile
    Optional file containing comment body.

.EXAMPLE
    .\Close-PR.ps1 -PullRequest 50

.EXAMPLE
    .\Close-PR.ps1 -PullRequest 50 -Comment "Superseded by #51"

.NOTES
    Exit Codes: 0=Success, 1=Invalid params, 2=Not found, 3=API error, 4=Not authenticated
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [int]$PullRequest,
    [string]$Comment,
    [string]$CommentFile
)

$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

# Validate CommentFile if provided
if ($CommentFile) {
    Assert-ValidBodyFile -BodyFile $CommentFile
    $Comment = Get-Content -Path $CommentFile -Raw
}

Write-Verbose "Closing PR #$PullRequest in $Owner/$Repo"

# Check current state first
$prState = gh pr view $PullRequest --repo "$Owner/$Repo" --json state 2>&1
if ($LASTEXITCODE -ne 0) {
    if ($prState -match "not found") {
        Write-ErrorAndExit "PR #$PullRequest not found in $Owner/$Repo" 2
    }
    Write-ErrorAndExit "Failed to get PR state: $prState" 3
}

$state = ($prState | ConvertFrom-Json).state

if ($state -eq "CLOSED" -or $state -eq "MERGED") {
    Write-Host "PR #$PullRequest is already $($state.ToLower())" -ForegroundColor Yellow
    [PSCustomObject]@{
        Success = $true
        Number = $PullRequest
        State = $state
        Action = "none"
        Message = "PR already $($state.ToLower())"
    } | ConvertTo-Json
    exit 0
}

# Post comment if provided
if ($Comment) {
    Write-Verbose "Posting close comment"
    $result = gh pr comment $PullRequest --repo "$Owner/$Repo" --body $Comment 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Failed to post comment: $result"
    }
}

# Close the PR
$result = gh pr close $PullRequest --repo "$Owner/$Repo" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-ErrorAndExit "Failed to close PR #$($PullRequest): $result" 3
}

Write-Host "Closed PR #$PullRequest" -ForegroundColor Green

[PSCustomObject]@{
    Success = $true
    Number = $PullRequest
    State = "CLOSED"
    Action = "closed"
    Message = "PR closed successfully"
} | ConvertTo-Json
