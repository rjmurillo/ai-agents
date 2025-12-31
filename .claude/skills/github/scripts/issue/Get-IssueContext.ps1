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

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubCore.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

Write-Verbose "Fetching issue #$Issue from $Owner/$Repo"

# Capture gh output directly - gh outputs valid JSON
$jsonResponse = gh issue view $Issue --repo "$Owner/$Repo" --json "number,title,body,state,author,labels,milestone,assignees,createdAt,updatedAt"

if ($LASTEXITCODE -ne 0) {
    Write-ErrorAndExit "Issue #$Issue not found or API error (exit code $LASTEXITCODE)" 2
}

# Parse JSON response
$issueData = ConvertFrom-Json -InputObject $jsonResponse

if (-not $issueData) {
    Write-ErrorAndExit "Failed to parse issue JSON" 3
}

$output = [PSCustomObject]@{
    Success   = $true
    Number    = $issueData.number
    Title     = $issueData.title
    Body      = $issueData.body
    State     = $issueData.state
    Author    = $issueData.author.login
    Labels    = @($issueData.labels | ForEach-Object { $_.name })
    Milestone = if ($issueData.milestone) { $issueData.milestone.title } else { $null }
    Assignees = @($issueData.assignees | ForEach-Object { $_.login })
    CreatedAt = $issueData.createdAt
    UpdatedAt = $issueData.updatedAt
    Owner     = $Owner
    Repo      = $Repo
}

Write-Output $output
Write-Host "Issue #$($output.Number): $($output.Title)" -ForegroundColor Cyan
Write-Host "  State: $($output.State) | Author: @$($output.Author)" -ForegroundColor Gray
if ($output.Labels.Count -gt 0) { Write-Host "  Labels: $($output.Labels -join ', ')" -ForegroundColor Yellow }
