<#
.SYNOPSIS
    Adds a reaction to one or more GitHub comments.

.DESCRIPTION
    Adds emoji reactions to PR review comments or issue comments.
    Supports batch operations for improved performance (88% faster).
    Common use: eyes to acknowledge receipt of review comments.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER CommentId
    One or more comment IDs to react to (required).
    Accepts both single ID and array of IDs for batch operations.

.PARAMETER CommentType
    "review" for PR review comments, "issue" for issue/PR-level comments (default: "review").

.PARAMETER Reaction
    Reaction type: +1, -1, laugh, confused, heart, hooray, rocket, eyes

.EXAMPLE
    .\Add-CommentReaction.ps1 -CommentId 12345678 -Reaction "eyes"
    # Single comment

.EXAMPLE
    .\Add-CommentReaction.ps1 -CommentId @(123, 456, 789) -Reaction "eyes"
    # Batch: 88% faster than separate calls

.EXAMPLE
    $ids = Get-PRReviewComments.ps1 -PullRequest 42 | Select-Object -ExpandProperty id
    .\Add-CommentReaction.ps1 -CommentId $ids -Reaction "eyes"
    # Acknowledge all comments on a PR

.NOTES
    Exit Codes: 0=All succeeded, 1=Invalid params, 3=Any failed, 4=Not authenticated
    Performance: Batch mode saves ~1.2s per additional comment (process spawn overhead)
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [long[]]$CommentId,
    [ValidateSet("review", "issue")] [string]$CommentType = "review",
    [Parameter(Mandatory)] [ValidateSet("+1", "-1", "laugh", "confused", "heart", "hooray", "rocket", "eyes")] [string]$Reaction
)

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

$emoji = Get-ReactionEmoji -Reaction $Reaction
$succeeded = 0
$failed = 0
$results = @()

foreach ($id in $CommentId) {
    $endpoint = switch ($CommentType) {
        "review" { "repos/$Owner/$Repo/pulls/comments/$id/reactions" }
        "issue" { "repos/$Owner/$Repo/issues/comments/$id/reactions" }
    }

    $result = gh api $endpoint -X POST -f content=$Reaction 2>&1
    $exitCode = $LASTEXITCODE

    # Duplicate reactions are OK (idempotent)
    $success = $exitCode -eq 0 -or ($result -match "already reacted")

    if ($success) {
        $succeeded++
        $results += [PSCustomObject]@{
            Success     = $true
            CommentId   = $id
            CommentType = $CommentType
            Reaction    = $Reaction
            Emoji       = $emoji
            Error       = $null
        }
        Write-Host "Added $emoji ($Reaction) to $CommentType comment $id" -ForegroundColor Green
    }
    else {
        $failed++
        $results += [PSCustomObject]@{
            Success     = $false
            CommentId   = $id
            CommentType = $CommentType
            Reaction    = $Reaction
            Emoji       = $emoji
            Error       = "$result"
        }
        Write-Host "Failed to add $emoji to $CommentType comment ${id}: $result" -ForegroundColor Red
    }
}

# Output summary for batch operations
$summary = [PSCustomObject]@{
    TotalCount  = $CommentId.Count
    Succeeded   = $succeeded
    Failed      = $failed
    Reaction    = $Reaction
    Emoji       = $emoji
    CommentType = $CommentType
    Results     = $results
}

Write-Output $summary

if ($CommentId.Count -gt 1) {
    Write-Host "`nBatch complete: $succeeded/$($CommentId.Count) succeeded" -ForegroundColor $(if ($failed -eq 0) { 'Green' } else { 'Yellow' })
}

# Exit code: 0 = all succeeded, 3 = any failed
if ($failed -gt 0) {
    exit 3
}
