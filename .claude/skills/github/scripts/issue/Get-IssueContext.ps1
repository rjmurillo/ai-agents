<#
.SYNOPSIS
    Gets context and metadata for a GitHub Issue.

.DESCRIPTION
    Retrieves issue information including title, body, labels, milestone, state.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER Issue
    Issue number (required).

.EXAMPLE
    .\Get-IssueContext.ps1 -Issue 123

.NOTES
    Exit Codes: 0=Success, 1=Invalid params, 2=Not found, 3=API error, 4=Not authenticated
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [int]$Issue
)

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

Write-Verbose "Fetching issue #$Issue from $Owner/$Repo"

$issueData = gh issue view $Issue --repo "$Owner/$Repo" --json number,title,body,state,author,labels,milestone,assignees,createdAt,updatedAt 2>&1

if ($LASTEXITCODE -ne 0) {
    if ($issueData -match "not found") { Write-ErrorAndExit "Issue #$Issue not found in $Owner/$Repo" 2 }
    Write-ErrorAndExit "Failed to get issue: $issueData" 3
}

$issue = $issueData | ConvertFrom-Json

$output = [PSCustomObject]@{
    Success   = $true
    Number    = $issue.number
    Title     = $issue.title
    Body      = $issue.body
    State     = $issue.state
    Author    = $issue.author.login
    Labels    = @($issue.labels | ForEach-Object { $_.name })
    Milestone = if ($issue.milestone) { $issue.milestone.title } else { $null }
    Assignees = @($issue.assignees | ForEach-Object { $_.login })
    CreatedAt = $issue.createdAt
    UpdatedAt = $issue.updatedAt
    Owner     = $Owner
    Repo      = $Repo
}

Write-Output $output
Write-Host "Issue #$($output.Number): $($output.Title)" -ForegroundColor Cyan
Write-Host "  State: $($output.State) | Author: @$($output.Author)" -ForegroundColor Gray
if ($output.Labels.Count -gt 0) { Write-Host "  Labels: $($output.Labels -join ', ')" -ForegroundColor Yellow }
