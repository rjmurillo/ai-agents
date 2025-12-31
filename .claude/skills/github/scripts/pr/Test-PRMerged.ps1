<#
.SYNOPSIS
    Checks if a GitHub Pull Request has been merged.

.DESCRIPTION
    Queries GitHub GraphQL API to determine PR merge state.
    Use this before starting PR review work to prevent wasted effort on merged PRs.
    Per Skill-PR-Review-007: gh pr view may return stale data.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER PullRequest
    PR number (required).

.EXAMPLE
    .\Test-PRMerged.ps1 -PullRequest 315

.EXAMPLE
    .\Test-PRMerged.ps1 -Owner rjmurillo -Repo ai-agents -PullRequest 315

.NOTES
    Exit Codes:
    - 0: PR is NOT merged (safe to proceed with review)
    - 1: PR IS merged (skip review work)
    - 2: Error occurred

    Source: Skill-PR-Review-007 (Session 85)
    Related: Issue #321
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [int]$PullRequest
)

$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubCore.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

# Use parameterized GraphQL query to prevent injection
$query = @'
query($owner: String!, $repo: String!, $prNumber: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $prNumber) {
      state
      merged
      mergedAt
      mergedBy {
        login
      }
    }
  }
}
'@

Write-Verbose "Querying GraphQL for PR #${PullRequest} merge state"

$result = gh api graphql -f query="$query" -f owner="$Owner" -f repo="$Repo" -F prNumber=$PullRequest 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-ErrorAndExit "GraphQL query failed: $result" 2
}

try {
    $pr = ($result | ConvertFrom-Json).data.repository.pullRequest

    if (-not $pr) {
        Write-ErrorAndExit "PR #$PullRequest not found in $Owner/$Repo. The query might have failed or the PR does not exist." 2
    }
}
catch {
    Write-ErrorAndExit "Failed to parse GraphQL response for PR #$PullRequest. Response: $result. Error: $_" 2
}

$output = [PSCustomObject]@{
    Success      = $true
    PullRequest  = $PullRequest
    Owner        = $Owner
    Repo         = $Repo
    State        = $pr.state
    Merged       = $pr.merged
    MergedAt     = $pr.mergedAt
    MergedBy     = if ($pr.mergedBy) { $pr.mergedBy.login } else { $null }
}

Write-Output $output

if ($pr.merged) {
    $mergedByText = if ($pr.mergedBy) { "@$($pr.mergedBy.login)" } else { "automated process" }
    Write-Host "[MERGED] PR #$PullRequest merged at $($pr.mergedAt) by $mergedByText" -ForegroundColor Yellow
    exit 1  # Exit code 1 = merged (skip review work)
} else {
    Write-Host "[NOT MERGED] PR #$PullRequest is not merged (state: $($pr.state))" -ForegroundColor Green
    exit 0  # Exit code 0 = not merged (safe to proceed)
}
