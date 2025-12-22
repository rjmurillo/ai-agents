<#
.SYNOPSIS
    Closes a GitHub Pull Request.

.DESCRIPTION
    Closes a PR, optionally deleting the head branch.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER PullRequest
    PR number (required).

.PARAMETER DeleteBranch
    If specified, deletes the head branch after closing the PR.

.PARAMETER Comment
    Optional comment to post before closing the PR.

.EXAMPLE
    .\Close-PR.ps1 -PullRequest 123

.EXAMPLE
    .\Close-PR.ps1 -PullRequest 123 -DeleteBranch -Comment "Closing as superseded by #456"

.NOTES
    Exit Codes: 0=Success, 1=Invalid params, 2=PR not found, 3=API error, 4=Not authenticated
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [int]$PullRequest,
    [switch]$DeleteBranch,
    [string]$Comment
)

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

# Post comment if provided
if (-not [string]::IsNullOrWhiteSpace($Comment)) {
    Write-Verbose "Posting comment before closing PR #$PullRequest"
    $commentResult = gh pr comment $PullRequest --repo "$Owner/$Repo" --body $Comment 2>&1

    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Failed to post comment: $commentResult"
        # Continue anyway - closing is more important
    }
}

# Close PR
$ghArgs = @('pr', 'close', $PullRequest, '--repo', "$Owner/$Repo")

if ($DeleteBranch) {
    $ghArgs += '--delete-branch'
}

$result = & gh @ghArgs 2>&1

if ($LASTEXITCODE -ne 0) {
    if ($result -match "not found") {
        Write-ErrorAndExit "PR #$PullRequest not found in $Owner/$Repo" 2
    }
    Write-ErrorAndExit "Failed to close PR: $result" 3
}

Write-Host "Closed PR #$PullRequest" -ForegroundColor Green

if ($DeleteBranch) {
    Write-Host "  Head branch deleted" -ForegroundColor Cyan
}

# GitHub Actions outputs for programmatic consumption
if ($env:GITHUB_OUTPUT) {
    Add-Content -Path $env:GITHUB_OUTPUT -Value "success=true"
    Add-Content -Path $env:GITHUB_OUTPUT -Value "pr=$PullRequest"
    Add-Content -Path $env:GITHUB_OUTPUT -Value "branch_deleted=$($DeleteBranch.ToString().ToLower())"
}
