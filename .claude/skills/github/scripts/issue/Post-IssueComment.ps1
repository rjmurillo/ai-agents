<#
.SYNOPSIS
    Posts a comment to a GitHub Issue with idempotency support.

.DESCRIPTION
    Posts comments to issues with optional marker for idempotency.
    If marker exists in existing comments, behavior depends on UpdateIfExists:
    - UpdateIfExists not specified: skips posting (write-once idempotency)
    - UpdateIfExists specified: updates existing comment (upsert behavior)

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

.PARAMETER UpdateIfExists
    When specified with Marker, updates the existing comment instead of skipping.
    Use this for CI/CD status comments that should reflect latest state.

.EXAMPLE
    .\Post-IssueComment.ps1 -Issue 123 -Body "Analysis complete."
    .\Post-IssueComment.ps1 -Issue 123 -BodyFile triage.md -Marker "AI-TRIAGE"
    .\Post-IssueComment.ps1 -Issue 123 -BodyFile status.md -Marker "CI-STATUS" -UpdateIfExists

.NOTES
    Exit Codes: 0=Success (including skip due to marker), 1=Invalid params, 2=File not found, 3=API error, 4=Not authenticated
#>

[CmdletBinding(DefaultParameterSetName = 'BodyText')]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [int]$Issue,
    [Parameter(ParameterSetName = 'BodyText', Mandatory)] [string]$Body,
    [Parameter(ParameterSetName = 'BodyFile', Mandatory)] [string]$BodyFile,
    [string]$Marker,
    [switch]$UpdateIfExists
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
    
    # Helper: Prepend marker to body if not already present
    function Add-MarkerToBody {
        param([string]$BodyContent, [string]$MarkerHtml)
        if ($BodyContent -notmatch [regex]::Escape($MarkerHtml)) {
            return "$MarkerHtml`n`n$BodyContent"
        }
        return $BodyContent
    }
    
    # Get all comments to check for existing marker
    $commentsJson = gh api "repos/$Owner/$Repo/issues/$Issue/comments" 2>$null
    
    if ($LASTEXITCODE -eq 0) {
        $comments = $commentsJson | ConvertFrom-Json
        $existingComment = $comments | Where-Object { $_.body -match [regex]::Escape($markerHtml) } | Select-Object -First 1
        
        if ($existingComment) {
            if ($UpdateIfExists) {
                # Update existing comment (upsert behavior for CI/CD status)
                Write-Host "Comment with marker '$Marker' exists. Updating..." -ForegroundColor Cyan
                
                $Body = Add-MarkerToBody -BodyContent $Body -MarkerHtml $markerHtml
                
                $response = Update-IssueComment -Owner $Owner -Repo $Repo -CommentId $existingComment.id -Body $Body
                
                Write-Host "Updated comment on issue #$Issue" -ForegroundColor Green
                Write-Host "  URL: $($response.html_url)" -ForegroundColor Cyan
                Write-Host "Success: True, Issue: $Issue, CommentId: $($response.id), Updated: True"
                
                # GitHub Actions outputs for programmatic consumption
                if ($env:GITHUB_OUTPUT) {
                    Add-Content -Path $env:GITHUB_OUTPUT -Value "success=true"
                    Add-Content -Path $env:GITHUB_OUTPUT -Value "skipped=false"
                    Add-Content -Path $env:GITHUB_OUTPUT -Value "updated=true"
                    Add-Content -Path $env:GITHUB_OUTPUT -Value "issue=$Issue"
                    Add-Content -Path $env:GITHUB_OUTPUT -Value "comment_id=$($response.id)"
                    Add-Content -Path $env:GITHUB_OUTPUT -Value "html_url=$($response.html_url)"
                    Add-Content -Path $env:GITHUB_OUTPUT -Value "updated_at=$($response.updated_at)"
                    Add-Content -Path $env:GITHUB_OUTPUT -Value "marker=$Marker"
                }
                
                exit 0
            } else {
                # Skip posting (write-once idempotency)
                Write-Host "Comment with marker '$Marker' already exists. Skipping." -ForegroundColor Yellow
                Write-Host "Success: True, Issue: $Issue, Marker: $Marker, Skipped: True"
                
                # GitHub Actions outputs for programmatic consumption
                if ($env:GITHUB_OUTPUT) {
                    Add-Content -Path $env:GITHUB_OUTPUT -Value "success=true"
                    Add-Content -Path $env:GITHUB_OUTPUT -Value "skipped=true"
                    Add-Content -Path $env:GITHUB_OUTPUT -Value "issue=$Issue"
                    Add-Content -Path $env:GITHUB_OUTPUT -Value "marker=$Marker"
                }
                
                exit 0  # Idempotent skip is a success
            }
        }
    }

    # Prepend marker for new comments
    $Body = Add-MarkerToBody -BodyContent $Body -MarkerHtml $markerHtml
}

# Post comment
$result = gh api "repos/$Owner/$Repo/issues/$Issue/comments" -X POST -f body=$Body 2>&1

if ($LASTEXITCODE -ne 0) { Write-ErrorAndExit "Failed to post comment: $result" 3 }

$response = $result | ConvertFrom-Json

Write-Host "Posted comment to issue #$Issue" -ForegroundColor Green
Write-Host "  URL: $($response.html_url)" -ForegroundColor Cyan
Write-Host "Success: True, Issue: $Issue, CommentId: $($response.id), Skipped: False"

# GitHub Actions outputs for programmatic consumption
if ($env:GITHUB_OUTPUT) {
    Add-Content -Path $env:GITHUB_OUTPUT -Value "success=true"
    Add-Content -Path $env:GITHUB_OUTPUT -Value "skipped=false"
    Add-Content -Path $env:GITHUB_OUTPUT -Value "issue=$Issue"
    Add-Content -Path $env:GITHUB_OUTPUT -Value "comment_id=$($response.id)"
    Add-Content -Path $env:GITHUB_OUTPUT -Value "html_url=$($response.html_url)"
    Add-Content -Path $env:GITHUB_OUTPUT -Value "created_at=$($response.created_at)"
    if ($Marker) {
        Add-Content -Path $env:GITHUB_OUTPUT -Value "marker=$Marker"
    }
}
