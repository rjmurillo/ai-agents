<#
.SYNOPSIS
    Merges a GitHub Pull Request.

.DESCRIPTION
    Merges a PR using the specified strategy. Supports auto-merge
    for PRs with pending checks.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER PullRequest
    PR number (required).

.PARAMETER Strategy
    Merge strategy: merge, squash, or rebase. Default: merge.

.PARAMETER DeleteBranch
    If specified, deletes the head branch after merge.

.PARAMETER Auto
    If specified, enables auto-merge (merge when checks pass).

.PARAMETER Subject
    Custom commit subject for merge/squash commits.

.PARAMETER Body
    Custom commit body for merge/squash commits.

.EXAMPLE
    .\Merge-PR.ps1 -PullRequest 50

.EXAMPLE
    .\Merge-PR.ps1 -PullRequest 50 -Strategy squash -DeleteBranch

.EXAMPLE
    .\Merge-PR.ps1 -PullRequest 50 -Auto

.NOTES
    Exit Codes: 0=Success, 1=Invalid params, 2=Not found, 3=API error, 4=Not authenticated, 6=Not mergeable
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [int]$PullRequest,
    [ValidateSet("merge", "squash", "rebase")]
    [string]$Strategy = "merge",
    [switch]$DeleteBranch,
    [switch]$Auto,
    [string]$Subject,
    [string]$Body
)

$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

Write-Verbose "Merging PR #$PullRequest in $Owner/$Repo with $Strategy strategy"

# Check PR state and mergeability
$prData = gh pr view $PullRequest --repo "$Owner/$Repo" --json state,mergeable,mergeStateStatus,headRefName 2>&1
if ($LASTEXITCODE -ne 0) {
    if ($prData -match "not found") {
        Write-ErrorAndExit "PR #$PullRequest not found in $Owner/$Repo" 2
    }
    Write-ErrorAndExit "Failed to get PR state: $prData" 3
}

$pr = $prData | ConvertFrom-Json

if ($pr.state -eq "MERGED") {
    Write-Host "PR #$PullRequest is already merged" -ForegroundColor Yellow
    [PSCustomObject]@{
        Success = $true
        Number = $PullRequest
        State = "MERGED"
        Action = "none"
        Message = "PR already merged"
    } | ConvertTo-Json
    exit 0
}

if ($pr.state -eq "CLOSED") {
    Write-ErrorAndExit "PR #$PullRequest is closed and cannot be merged" 6
}

# Build merge command
$mergeArgs = @($PullRequest, "--repo", "$Owner/$Repo", "--$Strategy")

if ($DeleteBranch) {
    $mergeArgs += "--delete-branch"
}

if ($Auto) {
    $mergeArgs += "--auto"
}

if ($Subject) {
    $mergeArgs += @("--subject", $Subject)
}

if ($Body) {
    $mergeArgs += @("--body", $Body)
}

# Execute merge
$result = gh pr merge @mergeArgs 2>&1
if ($LASTEXITCODE -ne 0) {
    if ($result -match "not mergeable|cannot be merged|conflicts") {
        Write-ErrorAndExit "PR #$PullRequest is not mergeable: $result" 6
    }
    Write-ErrorAndExit "Failed to merge PR #$($PullRequest): $result" 3
}

$action = if ($Auto) { "auto-merge-enabled" } else { "merged" }
Write-Host "PR #$PullRequest $action with $Strategy strategy" -ForegroundColor Green

[PSCustomObject]@{
    Success = $true
    Number = $PullRequest
    State = if ($Auto) { "PENDING" } else { "MERGED" }
    Action = $action
    Strategy = $Strategy
    BranchDeleted = [bool]$DeleteBranch
    Message = if ($Auto) { "Auto-merge enabled" } else { "PR merged successfully" }
} | ConvertTo-Json
