<#
.SYNOPSIS
    Posts a comment to a GitHub Pull Request.

.DESCRIPTION
    Posts comments to PRs with optional marker for idempotency.
    If marker exists in existing comments, skips posting.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER PullRequest
    PR number (required).

.PARAMETER Body
    Comment text (inline). Mutually exclusive with BodyFile.

.PARAMETER BodyFile
    Path to file containing comment. Mutually exclusive with Body.

.PARAMETER Marker
    HTML comment marker for idempotency (e.g., "PR-MAINTENANCE").

.EXAMPLE
    .\Post-PRComment.ps1 -PullRequest 123 -Body "Closing as superseded by #456"

.EXAMPLE
    .\Post-PRComment.ps1 -PullRequest 123 -BodyFile comment.md -Marker "PR-MAINTENANCE"

.NOTES
    Exit Codes: 0=Success (including skip due to marker), 1=Invalid params, 2=File not found, 3=API error, 4=Not authenticated
#>

[CmdletBinding(DefaultParameterSetName = 'BodyText')]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [int]$PullRequest,
    [Parameter(ParameterSetName = 'BodyText', Mandatory)] [string]$Body,
    [Parameter(ParameterSetName = 'BodyFile', Mandatory)] [string]$BodyFile,
    [string]$Marker
)

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

# Resolve body
if ($BodyFile) {
    if (-not (Test-Path $BodyFile)) {
        Write-ErrorAndExit "Body file not found: $BodyFile" 2
    }
    $Body = Get-Content -Path $BodyFile -Raw -Encoding UTF8
}

if ([string]::IsNullOrWhiteSpace($Body)) {
    Write-ErrorAndExit "Body cannot be empty." 1
}

# Check idempotency marker
if ($Marker) {
    $markerHtml = "<!-- $Marker -->"
    $existingComments = gh api "repos/$Owner/$Repo/issues/$PullRequest/comments" --jq ".[].body" 2>$null

    if ($LASTEXITCODE -eq 0 -and $existingComments -match [regex]::Escape($markerHtml)) {
        Write-Host "Comment with marker '$Marker' already exists. Skipping." -ForegroundColor Yellow
        Write-Host "Success: True, PR: $PullRequest, Marker: $Marker, Skipped: True"

        # GitHub Actions outputs for programmatic consumption
        if ($env:GITHUB_OUTPUT) {
            Add-Content -Path $env:GITHUB_OUTPUT -Value "success=true"
            Add-Content -Path $env:GITHUB_OUTPUT -Value "skipped=true"
            Add-Content -Path $env:GITHUB_OUTPUT -Value "pr=$PullRequest"
            Add-Content -Path $env:GITHUB_OUTPUT -Value "marker=$Marker"
        }

        exit 0  # Idempotent skip is a success
    }

    # Prepend marker if not in body
    if ($Body -notmatch [regex]::Escape($markerHtml)) {
        $Body = "$markerHtml`n`n$Body"
    }
}

# Post comment
$result = gh pr comment $PullRequest --repo "$Owner/$Repo" --body $Body 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-ErrorAndExit "Failed to post comment: $result" 3
}

Write-Host "Posted comment to PR #$PullRequest" -ForegroundColor Green
Write-Host "Success: True, PR: $PullRequest, Skipped: False"

# GitHub Actions outputs for programmatic consumption
if ($env:GITHUB_OUTPUT) {
    Add-Content -Path $env:GITHUB_OUTPUT -Value "success=true"
    Add-Content -Path $env:GITHUB_OUTPUT -Value "skipped=false"
    Add-Content -Path $env:GITHUB_OUTPUT -Value "pr=$PullRequest"
    if ($Marker) {
        Add-Content -Path $env:GITHUB_OUTPUT -Value "marker=$Marker"
    }
}
