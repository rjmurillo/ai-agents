<#
.SYNOPSIS
    Creates a new GitHub Issue.

.DESCRIPTION
    Creates issues with title, body, and labels.
    Supports both inline body text and file-based body content.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER Title
    Issue title (required).

.PARAMETER Body
    Issue body text (inline). Mutually exclusive with BodyFile.

.PARAMETER BodyFile
    Path to file containing issue body. Mutually exclusive with Body.

.PARAMETER Labels
    Comma-separated list of labels to apply (e.g., "bug,P1,needs-triage").

.EXAMPLE
    .\New-Issue.ps1 -Title "Bug: Login fails" -Body "Steps to reproduce..." -Labels "bug,P1"

.EXAMPLE
    .\New-Issue.ps1 -Title "Feature Request" -BodyFile feature.md -Labels "enhancement"

.NOTES
    Exit Codes: 0=Success, 1=Invalid params, 2=File not found, 3=API error, 4=Not authenticated
#>

[CmdletBinding(DefaultParameterSetName = 'BodyText')]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [string]$Title,
    [Parameter(ParameterSetName = 'BodyText')] [string]$Body = "",
    [Parameter(ParameterSetName = 'BodyFile', Mandatory)] [string]$BodyFile,
    [string]$Labels = ""
)

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

if ([string]::IsNullOrWhiteSpace($Title)) {
    Write-ErrorAndExit "Title cannot be empty." 1
}

# Resolve body
if ($BodyFile) {
    if (-not (Test-Path $BodyFile)) {
        Write-ErrorAndExit "Body file not found: $BodyFile" 2
    }
    $Body = Get-Content -Path $BodyFile -Raw -Encoding UTF8
}

# Build gh issue create command
$ghArgs = @('issue', 'create', '--repo', "$Owner/$Repo", '--title', $Title)

if (-not [string]::IsNullOrWhiteSpace($Body)) {
    $ghArgs += '--body', $Body
}

if (-not [string]::IsNullOrWhiteSpace($Labels)) {
    $ghArgs += '--label', $Labels
}

# Create issue
$result = & gh @ghArgs 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-ErrorAndExit "Failed to create issue: $result" 3
}

# Parse issue URL to extract issue number (gh issue create outputs URL format: https://github.com/owner/repo/issues/123)
if ($result -match 'issues/(\d+)') {
    $issueNumber = [int]$Matches[1]
}
else {
    Write-ErrorAndExit "Could not parse issue number from result: $result" 3
}

Write-Host "Created issue #$issueNumber" -ForegroundColor Green
Write-Host "  Title: $Title" -ForegroundColor Cyan
Write-Host "  URL: $result" -ForegroundColor Cyan

# GitHub Actions outputs for programmatic consumption
if ($env:GITHUB_OUTPUT) {
    Add-Content -Path $env:GITHUB_OUTPUT -Value "success=true"
    Add-Content -Path $env:GITHUB_OUTPUT -Value "issue_number=$issueNumber"
    Add-Content -Path $env:GITHUB_OUTPUT -Value "issue_url=$result"
}
