<#
.SYNOPSIS
    Enables or disables auto-merge for a GitHub Pull Request.

.DESCRIPTION
    Uses GitHub GraphQL API to enable or disable auto-merge on a PR.
    Auto-merge will automatically merge the PR once all required status
    checks pass and required reviews are approved.

    Requires:
    - Auto-merge must be enabled in repository settings
    - User must have write access to the repository
    - Branch protection rules with required checks or reviews

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER PullRequest
    PR number (required).

.PARAMETER Enable
    Enable auto-merge for the PR.

.PARAMETER Disable
    Disable auto-merge for the PR.

.PARAMETER MergeMethod
    Merge method to use: MERGE, SQUASH, or REBASE. Default: SQUASH.

.PARAMETER CommitHeadline
    Optional custom commit headline for squash/merge commits.

.PARAMETER CommitBody
    Optional custom commit body for squash/merge commits.

.EXAMPLE
    ./Set-PRAutoMerge.ps1 -PullRequest 50 -Enable

.EXAMPLE
    ./Set-PRAutoMerge.ps1 -PullRequest 50 -Enable -MergeMethod MERGE

.EXAMPLE
    ./Set-PRAutoMerge.ps1 -PullRequest 50 -Disable

.EXAMPLE
    ./Set-PRAutoMerge.ps1 -PullRequest 50 -Enable -CommitHeadline "feat: Add feature (#50)"

.NOTES
    Exit Codes:
      0 - Success
      1 - Invalid params
      2 - PR not found
      3 - API error (e.g., auto-merge not enabled in repo)
      4 - Not authenticated
#>

[CmdletBinding(DefaultParameterSetName = 'Enable')]
param(
    [string]$Owner,
    [string]$Repo,

    [Parameter(Mandatory)]
    [int]$PullRequest,

    [Parameter(ParameterSetName = 'Enable', Mandatory)]
    [switch]$Enable,

    [Parameter(ParameterSetName = 'Disable', Mandatory)]
    [switch]$Disable,

    [Parameter(ParameterSetName = 'Enable')]
    [ValidateSet('MERGE', 'SQUASH', 'REBASE')]
    [string]$MergeMethod = 'SQUASH',

    [Parameter(ParameterSetName = 'Enable')]
    [string]$CommitHeadline,

    [Parameter(ParameterSetName = 'Enable')]
    [string]$CommitBody
)

$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

Write-Verbose "Setting auto-merge for PR #$PullRequest in $Owner/$Repo"

# First get the PR node ID (required for GraphQL mutations)
$prQuery = @'
query($owner: String!, $repo: String!, $number: Int!) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
            id
            number
            state
            autoMergeRequest {
                enabledAt
                mergeMethod
            }
        }
    }
}
'@

try {
    $prParsed = Invoke-GhGraphQL -Query $prQuery -Variables @{
        owner  = $Owner
        repo   = $Repo
        number = $PullRequest
    }
}
catch {
    $errorMsg = $_.Exception.Message
    if ($errorMsg -match "Could not resolve") {
        Write-ErrorAndExit "PR #$PullRequest not found in $Owner/$Repo" 2
    }
    Write-ErrorAndExit "Failed to get PR info: $errorMsg" 3
}

$pr = $prParsed.data.repository.pullRequest
if ($null -eq $pr) {
    Write-ErrorAndExit "PR #$PullRequest not found" 2
}

$prId = $pr.id

if ($Disable) {
    # Disable auto-merge
    if ($null -eq $pr.autoMergeRequest) {
        Write-Host "Auto-merge is not enabled on PR #$PullRequest" -ForegroundColor Yellow
        $output = [PSCustomObject]@{
            Success = $true
            Action = 'NoChange'
            PullRequest = $PullRequest
            AutoMergeEnabled = $false
            Message = 'Auto-merge was already disabled'
        }
        $output | ConvertTo-Json -Depth 5
        exit 0
    }

    $disableMutation = @'
mutation($pullRequestId: ID!) {
    disablePullRequestAutoMerge(input: {pullRequestId: $pullRequestId}) {
        pullRequest {
            id
            number
            autoMergeRequest {
                enabledAt
            }
        }
    }
}
'@

    try {
        $disableParsed = Invoke-GhGraphQL -Query $disableMutation -Variables @{
            pullRequestId = $prId
        }
    }
    catch {
        Write-ErrorAndExit "Failed to disable auto-merge: $($_.Exception.Message)" 3
    }

    $disabled = $null -eq $disableParsed.data.disablePullRequestAutoMerge.pullRequest.autoMergeRequest

    $output = [PSCustomObject]@{
        Success = $disabled
        Action = 'Disabled'
        PullRequest = $PullRequest
        AutoMergeEnabled = -not $disabled
    }

    $output | ConvertTo-Json -Depth 5

    if ($disabled) {
        Write-Host "Auto-merge disabled for PR #$PullRequest" -ForegroundColor Green
    }
    else {
        Write-Host "Failed to disable auto-merge for PR #$PullRequest" -ForegroundColor Red
        exit 1
    }
}
else {
    # Enable auto-merge
    # Build the mutation input
    $enableMutation = @'
mutation($pullRequestId: ID!, $mergeMethod: PullRequestMergeMethod!, $commitHeadline: String, $commitBody: String) {
    enablePullRequestAutoMerge(input: {
        pullRequestId: $pullRequestId,
        mergeMethod: $mergeMethod,
        commitHeadline: $commitHeadline,
        commitBody: $commitBody
    }) {
        pullRequest {
            id
            number
            autoMergeRequest {
                enabledAt
                mergeMethod
            }
        }
    }
}
'@

    # Build variables hashtable with optional parameters
    $vars = @{
        pullRequestId = $prId
        mergeMethod   = $MergeMethod
        commitHeadline = if ($CommitHeadline) { $CommitHeadline } else { "" }
        commitBody     = if ($CommitBody) { $CommitBody } else { "" }
    }

    try {
        $enableParsed = Invoke-GhGraphQL -Query $enableMutation -Variables $vars
    }
    catch {
        $errorMsg = $_.Exception.Message
        # Check for common error cases
        if ($errorMsg -match "Auto-merge is not allowed") {
            Write-ErrorAndExit "Auto-merge is not enabled in repository settings. Enable it in Settings -> General -> Pull Requests." 3
        }
        if ($errorMsg -match "not mergeable") {
            Write-ErrorAndExit "PR is not in a mergeable state. Check for conflicts or required reviews." 3
        }
        Write-ErrorAndExit "Failed to enable auto-merge: $errorMsg" 3
    }

    $autoMerge = $enableParsed.data.enablePullRequestAutoMerge.pullRequest.autoMergeRequest
    $enabled = $null -ne $autoMerge

    $output = [PSCustomObject]@{
        Success = $enabled
        Action = 'Enabled'
        PullRequest = $PullRequest
        AutoMergeEnabled = $enabled
        MergeMethod = if ($autoMerge) { $autoMerge.mergeMethod } else { $null }
        EnabledAt = if ($autoMerge) { $autoMerge.enabledAt } else { $null }
    }

    $output | ConvertTo-Json -Depth 5

    if ($enabled) {
        Write-Host "Auto-merge enabled for PR #$PullRequest" -ForegroundColor Green
        Write-Host "  Method: $($autoMerge.mergeMethod)" -ForegroundColor Gray
        Write-Host "  Enabled at: $($autoMerge.enabledAt)" -ForegroundColor Gray
    }
    else {
        Write-Host "Failed to enable auto-merge for PR #$PullRequest" -ForegroundColor Red
        exit 1
    }
}
