<#
.SYNOPSIS
    Assigns users to a GitHub Issue.

.DESCRIPTION
    Manages assignees on GitHub Issues:
    - Adds one or more assignees to an issue
    - Supports @me shorthand for current authenticated user
    - Validates assignees are valid GitHub usernames

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER Issue
    Issue number (required).

.PARAMETER Assignees
    Array of GitHub usernames to assign. Use "@me" for current user.

.EXAMPLE
    .\Set-IssueAssignee.ps1 -Issue 123 -Assignees @("@me")
    .\Set-IssueAssignee.ps1 -Issue 123 -Assignees @("user1", "user2")

.NOTES
    Exit Codes: 0=Success, 1=Invalid params, 3=API error, 4=Not authenticated
    
    See: ADR-035 Exit Code Standardization
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [int]$Issue,
    [Parameter(Mandatory)] [string[]]$Assignees
)

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubCore.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

# gh CLI supports @me natively, no resolution needed
if ($Assignees.Count -eq 0) {
    Write-Warning "No assignees to add."
    exit 0
}

$applied = @()
$failed = @()

foreach ($assignee in $Assignees) {
    $null = gh issue edit $Issue --repo "$Owner/$Repo" --add-assignee $assignee 2>&1
    if ($LASTEXITCODE -eq 0) {
        $applied += $assignee
    }
    else {
        $failed += $assignee
    }
}

$output = [PSCustomObject]@{
    Success       = $failed.Count -eq 0
    Issue         = $Issue
    Applied       = $applied
    Failed        = $failed
    TotalApplied  = $applied.Count
}

Write-Output $output
if ($applied.Count -gt 0) {
    Write-Host "Assigned $($applied.Count) user(s) to issue #${Issue}: $($applied -join ', ')" -ForegroundColor Green
}
if ($failed.Count -gt 0) {
    Write-Host "Failed to assign: $($failed -join ', ')" -ForegroundColor Red
    exit 3
}
