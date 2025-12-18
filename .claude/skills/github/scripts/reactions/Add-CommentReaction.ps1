<#
.SYNOPSIS
    Adds a reaction to a GitHub comment.

.DESCRIPTION
    Adds emoji reactions to PR review comments or issue comments.
    Common use: 👀 (eyes) to acknowledge receipt of review comments.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER CommentId
    The comment ID to react to (required).

.PARAMETER CommentType
    "review" for PR review comments, "issue" for issue/PR-level comments (default: "review").

.PARAMETER Reaction
    Reaction type: +1, -1, laugh, confused, heart, hooray, rocket, eyes

.EXAMPLE
    .\Add-CommentReaction.ps1 -CommentId 12345678 -Reaction "eyes"
    .\Add-CommentReaction.ps1 -CommentId 12345678 -CommentType "issue" -Reaction "+1"

.NOTES
    Exit Codes: 0=Success, 1=Invalid params, 3=API error, 4=Not authenticated
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [long]$CommentId,
    [ValidateSet("review", "issue")] [string]$CommentType = "review",
    [Parameter(Mandatory)] [ValidateSet("+1", "-1", "laugh", "confused", "heart", "hooray", "rocket", "eyes")] [string]$Reaction
)

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

$endpoint = switch ($CommentType) {
    "review" { "repos/$Owner/$Repo/pulls/comments/$CommentId/reactions" }
    "issue" { "repos/$Owner/$Repo/issues/comments/$CommentId/reactions" }
}

$result = gh api $endpoint -X POST -f content=$Reaction 2>&1

# Duplicate reactions are OK (idempotent)
if ($LASTEXITCODE -ne 0 -and -not ($result -match "already reacted")) {
    Write-ErrorAndExit "Failed to add reaction: $result" 3
}

$emoji = Get-ReactionEmoji -Reaction $Reaction

$output = [PSCustomObject]@{
    Success     = $true
    CommentId   = $CommentId
    CommentType = $CommentType
    Reaction    = $Reaction
    Emoji       = $emoji
}

Write-Output $output
Write-Host "Added $emoji ($Reaction) to $CommentType comment $CommentId" -ForegroundColor Green
