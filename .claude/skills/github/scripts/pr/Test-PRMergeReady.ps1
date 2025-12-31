<#
.SYNOPSIS
    Checks if a PR is ready to merge.

.DESCRIPTION
    Performs comprehensive merge readiness check:
    - Verifies all review threads are resolved
    - Checks CI status (required checks passing by default)
    - Validates PR state (open, not draft)
    - Checks for merge conflicts

    By default, only REQUIRED checks block merge. Non-required failing checks
    are reported but don't affect CanMerge unless -IncludeNonRequired is set.

    Returns a structured result with CanMerge boolean and reasons.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER PullRequest
    PR number (required).

.PARAMETER IgnoreCI
    If specified, skips CI check verification entirely.

.PARAMETER IgnoreThreads
    If specified, skips unresolved thread check.

.PARAMETER IncludeNonRequired
    If specified, non-required check failures also block merge.
    Default behavior only blocks on required checks.

.EXAMPLE
    ./Test-PRMergeReady.ps1 -PullRequest 50
    # Only blocks if required checks fail

.EXAMPLE
    ./Test-PRMergeReady.ps1 -PullRequest 50 -IncludeNonRequired
    # Blocks if any check (required or not) fails

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
    [switch]$IgnoreThreads,
    [switch]$IncludeNonRequired
)

$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubCore.psm1") -Force

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
    $prData = Invoke-GhGraphQL -Query $query -Variables @{ owner = $Owner; repo = $Repo; number = $PullRequest }
}
catch {
    if ($_.Exception.Message -match "Could not resolve") {
        Write-ErrorAndExit "PR #$PullRequest not found in $Owner/$Repo" 2
    }
    Write-ErrorAndExit "Failed to query PR status: $($_.Exception.Message)" 3
}

$pr = $prData.repository.pullRequest
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
# Separate tracking for required vs non-required checks
$failedRequiredChecks = [System.Collections.Generic.List[string]]::new()
$pendingRequiredChecks = [System.Collections.Generic.List[string]]::new()
$failedNonRequiredChecks = [System.Collections.Generic.List[string]]::new()
$pendingNonRequiredChecks = [System.Collections.Generic.List[string]]::new()
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
                    if ($ctx.isRequired) {
                        $pendingRequiredChecks.Add($ctx.name)
                    } else {
                        $pendingNonRequiredChecks.Add($ctx.name)
                    }
                }
                elseif ($ctx.conclusion -notin @('SUCCESS', 'NEUTRAL', 'SKIPPED')) {
                    if ($ctx.isRequired) {
                        $failedRequiredChecks.Add($ctx.name)
                    } else {
                        $failedNonRequiredChecks.Add($ctx.name)
                    }
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
                    if ($ctx.isRequired) {
                        $pendingRequiredChecks.Add($ctx.context)
                    } else {
                        $pendingNonRequiredChecks.Add($ctx.context)
                    }
                }
                elseif ($ctx.state -notin @('SUCCESS', 'EXPECTED')) {
                    if ($ctx.isRequired) {
                        $failedRequiredChecks.Add($ctx.context)
                    } else {
                        $failedNonRequiredChecks.Add($ctx.context)
                    }
                }
                else {
                    $passedChecks++
                }
            }
        }

        # Always block on required check failures
        if ($failedRequiredChecks.Count -gt 0) {
            $reasons.Add("$($failedRequiredChecks.Count) required CI check(s) failed: $($failedRequiredChecks -join ', ')")
            $ciPassing = $false
        }
        if ($pendingRequiredChecks.Count -gt 0) {
            $reasons.Add("$($pendingRequiredChecks.Count) required CI check(s) pending: $($pendingRequiredChecks -join ', ')")
            $ciPassing = $false
        }

        # Only block on non-required checks if -IncludeNonRequired is specified
        if ($IncludeNonRequired) {
            if ($failedNonRequiredChecks.Count -gt 0) {
                $reasons.Add("$($failedNonRequiredChecks.Count) non-required CI check(s) failed: $($failedNonRequiredChecks -join ', ')")
                $ciPassing = $false
            }
            if ($pendingNonRequiredChecks.Count -gt 0) {
                $reasons.Add("$($pendingNonRequiredChecks.Count) non-required CI check(s) pending: $($pendingNonRequiredChecks -join ', ')")
                $ciPassing = $false
            }
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
    FailedRequiredChecks = @($failedRequiredChecks)
    PendingRequiredChecks = @($pendingRequiredChecks)
    FailedNonRequiredChecks = @($failedNonRequiredChecks)
    PendingNonRequiredChecks = @($pendingNonRequiredChecks)
    PassedChecks = $passedChecks
    CIPassing = $ciPassing
    IncludeNonRequired = $IncludeNonRequired.IsPresent
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
