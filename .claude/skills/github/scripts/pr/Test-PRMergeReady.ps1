<#
.SYNOPSIS
    Checks if a PR is ready to merge.

.DESCRIPTION
    Performs comprehensive merge readiness check:
    - Verifies all review threads are resolved
    - Checks CI status (all checks passing)
    - Validates PR state (open, not draft)
    - Checks for merge conflicts

    Returns a structured result with CanMerge boolean and reasons.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER PullRequest
    PR number (required).

.PARAMETER IgnoreCI
    If specified, skips CI check verification.

.PARAMETER IgnoreThreads
    If specified, skips unresolved thread check.

.EXAMPLE
    ./Test-PRMergeReady.ps1 -PullRequest 50

.EXAMPLE
    ./Test-PRMergeReady.ps1 -PullRequest 50 -IgnoreCI

.NOTES
    Exit Codes:
      0 - PR is ready to merge
      1 - PR is not ready to merge (see Reasons in output)
      2 - PR not found
      3 - API error
      4 - Not authenticated
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)]
    [int]$PullRequest,
    [switch]$IgnoreCI,
    [switch]$IgnoreThreads
)

$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

Write-Verbose "Checking merge readiness for PR #$PullRequest in $Owner/$Repo"

# GraphQL query to get PR state, threads, and CI status in one call
# Uses GraphQL variables for security (prevents injection via Owner/Repo/PR)
$query = @'
query($owner: String!, $repo: String!, $number: Int!) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
            number
            state
            isDraft
            mergeable
            mergeStateStatus
            reviewThreads(first: 100) {
                totalCount
                nodes {
                    id
                    isResolved
                }
            }
            commits(last: 1) {
                nodes {
                    commit {
                        statusCheckRollup {
                            state
                            contexts(first: 100) {
                                nodes {
                                    ... on CheckRun {
                                        __typename
                                        name
                                        status
                                        conclusion
                                        isRequired(pullRequestNumber: $number)
                                    }
                                    ... on StatusContext {
                                        __typename
                                        context
                                        state
                                        isRequired(pullRequestNumber: $number)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
'@

try {
    $parsed = Invoke-GhGraphQL -Query $query -Variables @{
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
    Write-ErrorAndExit "Failed to query PR status: $errorMsg" 3
}

$pr = $parsed.data.repository.pullRequest
if ($null -eq $pr) {
    Write-ErrorAndExit "PR #$PullRequest not found" 2
}

# Collect blocking reasons
$reasons = [System.Collections.Generic.List[string]]::new()
$checks = @()
$threads = @()

# Check 1: PR State
if ($pr.state -ne 'OPEN') {
    $reasons.Add("PR is $($pr.state.ToLower()), not open")
}

if ($pr.isDraft) {
    $reasons.Add("PR is in draft state")
}

# Check 2: Merge conflicts
if ($pr.mergeable -eq 'CONFLICTING') {
    $reasons.Add("PR has merge conflicts")
}
elseif ($pr.mergeable -eq 'UNKNOWN') {
    $reasons.Add("Merge status is being calculated")
}

# Check 3: Review Threads
$unresolvedCount = 0
if (-not $IgnoreThreads -and $pr.reviewThreads -and $pr.reviewThreads.nodes) {
    $threads = @($pr.reviewThreads.nodes)
    $unresolvedCount = @($threads | Where-Object { -not $_.isResolved }).Count
    if ($unresolvedCount -gt 0) {
        $reasons.Add("$unresolvedCount unresolved review thread(s)")
    }
}

# Check 4: CI Status
$failedChecks = @()
$pendingChecks = @()
$passedChecks = 0
$ciPassing = $true

if (-not $IgnoreCI) {
    $commit = $pr.commits.nodes | Select-Object -First 1
    if ($commit -and $commit.commit.statusCheckRollup) {
        $rollup = $commit.commit.statusCheckRollup
        $contexts = $rollup.contexts.nodes

        foreach ($ctx in $contexts) {
            if ($ctx.__typename -eq 'CheckRun') {
                $checkInfo = @{
                    Name = $ctx.name
                    Status = $ctx.status
                    Conclusion = $ctx.conclusion
                    IsRequired = $ctx.isRequired
                }
                $checks += $checkInfo

                if ($ctx.status -ne 'COMPLETED') {
                    $pendingChecks += $ctx.name
                }
                elseif ($ctx.conclusion -notin @('SUCCESS', 'NEUTRAL', 'SKIPPED')) {
                    $failedChecks += $ctx.name
                }
                else {
                    $passedChecks++
                }
            }
            elseif ($ctx.__typename -eq 'StatusContext') {
                $checkInfo = @{
                    Name = $ctx.context
                    State = $ctx.state
                    IsRequired = $ctx.isRequired
                }
                $checks += $checkInfo

                if ($ctx.state -eq 'PENDING') {
                    $pendingChecks += $ctx.context
                }
                elseif ($ctx.state -notin @('SUCCESS', 'EXPECTED')) {
                    $failedChecks += $ctx.context
                }
                else {
                    $passedChecks++
                }
            }
        }

        if ($failedChecks.Count -gt 0) {
            $reasons.Add("$($failedChecks.Count) CI check(s) failed: $($failedChecks -join ', ')")
            $ciPassing = $false
        }
        if ($pendingChecks.Count -gt 0) {
            $reasons.Add("$($pendingChecks.Count) CI check(s) pending: $($pendingChecks -join ', ')")
            $ciPassing = $false
        }
    }
}

# Determine final result
$canMerge = $reasons.Count -eq 0

# Build output
$output = [PSCustomObject]@{
    Success = $true
    CanMerge = $canMerge
    PullRequest = $PullRequest
    Owner = $Owner
    Repo = $Repo
    State = $pr.state
    IsDraft = $pr.isDraft
    Mergeable = $pr.mergeable
    MergeStateStatus = $pr.mergeStateStatus
    UnresolvedThreads = $unresolvedCount
    TotalThreads = $pr.reviewThreads.totalCount
    FailedChecks = @($failedChecks)
    PendingChecks = @($pendingChecks)
    PassedChecks = $passedChecks
    CIPassing = $ciPassing
    Reasons = @($reasons)
}

$output | ConvertTo-Json -Depth 5

# Summary output
if ($canMerge) {
    Write-Host "PR #$PullRequest is READY to merge" -ForegroundColor Green
}
else {
    Write-Host "PR #$PullRequest is NOT ready to merge" -ForegroundColor Red
    foreach ($reason in $reasons) {
        Write-Host "  - $reason" -ForegroundColor Yellow
    }
}

exit $(if ($canMerge) { 0 } else { 1 })
