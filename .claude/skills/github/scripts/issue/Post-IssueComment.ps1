<#
.SYNOPSIS
    Posts a comment to a GitHub Issue with idempotency support.

.DESCRIPTION
    Posts comments to issues with optional marker for idempotency.
    If marker exists in existing comments, skips posting.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER Issue
    Issue number (required).

.PARAMETER Body
    Comment text (inline). Mutually exclusive with BodyFile.

.PARAMETER BodyFile
    Path to file containing comment. Mutually exclusive with Body.

.PARAMETER Marker
    HTML comment marker for idempotency (e.g., "AI-TRIAGE").

.EXAMPLE
    .\Post-IssueComment.ps1 -Issue 123 -Body "Analysis complete."
    .\Post-IssueComment.ps1 -Issue 123 -BodyFile triage.md -Marker "AI-TRIAGE"

.NOTES
    Exit Codes: 0=Success, 1=Invalid params, 2=File not found, 3=API error, 4=Not authenticated, 5=Marker exists
#>

[CmdletBinding(DefaultParameterSetName = 'BodyText')]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [int]$Issue,
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
    if (-not (Test-Path $BodyFile)) { Write-ErrorAndExit "Body file not found: $BodyFile" 2 }
    $Body = Get-Content -Path $BodyFile -Raw -Encoding UTF8
}

if ([string]::IsNullOrWhiteSpace($Body)) { Write-ErrorAndExit "Body cannot be empty." 1 }

# Check idempotency marker
if ($Marker) {
    $markerHtml = "<!-- $Marker -->"
    $existingComments = gh api "repos/$Owner/$Repo/issues/$Issue/comments" --jq ".[].body" 2>$null

    if ($LASTEXITCODE -eq 0 -and $existingComments -match [regex]::Escape($markerHtml)) {
        Write-Host "Comment with marker '$Marker' already exists. Skipping." -ForegroundColor Yellow
        $output = [PSCustomObject]@{ Success = $true; Issue = $Issue; Marker = $Marker; Skipped = $true }
        Write-Output $output
        exit 5
    }

    # Prepend marker if not in body
    if ($Body -notmatch [regex]::Escape($markerHtml)) {
        $Body = "$markerHtml`n`n$Body"
    }
}

# Post comment
$result = gh api "repos/$Owner/$Repo/issues/$Issue/comments" -X POST -f body=$Body 2>&1

if ($LASTEXITCODE -ne 0) { Write-ErrorAndExit "Failed to post comment: $result" 3 }

$response = $result | ConvertFrom-Json

$output = [PSCustomObject]@{
    Success   = $true
    CommentId = $response.id
    HtmlUrl   = $response.html_url
    Issue     = $Issue
    Marker    = $Marker
    Skipped   = $false
    CreatedAt = $response.created_at
}

Write-Output $output
Write-Host "Posted comment to issue #$Issue" -ForegroundColor Green
Write-Host "  URL: $($output.HtmlUrl)" -ForegroundColor Cyan
