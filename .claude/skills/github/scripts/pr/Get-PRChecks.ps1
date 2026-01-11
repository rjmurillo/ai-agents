<#
.SYNOPSIS
    Gets CI check status for a GitHub Pull Request.

.DESCRIPTION
    Retrieves CI check information using GraphQL statusCheckRollup API.
    Returns structured JSON with check states, conclusions, and summary counts.
    Supports polling until checks complete and filtering to required checks only.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER PullRequest
    PR number (required).

.PARAMETER Wait
    If specified, polls until all checks complete or timeout is reached.

.PARAMETER TimeoutSeconds
    Maximum wait time when -Wait is specified. Default: 300 seconds (5 minutes).

.PARAMETER RequiredOnly
    If specified, filters output to required checks only.

.EXAMPLE
    .\Get-PRChecks.ps1 -PullRequest 50

.EXAMPLE
    .\Get-PRChecks.ps1 -PullRequest 50 -Wait -TimeoutSeconds 600

.EXAMPLE
    .\Get-PRChecks.ps1 -PullRequest 50 -RequiredOnly

.NOTES
    Exit Codes:
      0 - All checks passing (or skipped)
      1 - One or more checks failed
      2 - PR not found
      3 - API error
      7 - Timeout reached (with -Wait)

    Uses GraphQL statusCheckRollup which provides both GitHub Actions CheckRuns
    and legacy Status API contexts in a unified format.
    
    See: ADR-035 Exit Code Standardization
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)]
    [int]$PullRequest,
    [switch]$Wait,
    [int]$TimeoutSeconds = 300,
    [switch]$RequiredOnly
)

$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubCore.psm1") -Force

#region Helper Functions

# GraphQL query for status check rollup
$query = @'
query($owner: String!, $repo: String!, $number: Int!) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
            number
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
                                        detailsUrl
                                        isRequired(pullRequestNumber: $number)
                                    }
                                    ... on StatusContext {
                                        __typename
                                        context
                                        state
                                        targetUrl
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

#endregion

function Get-SafeProperty {
    <#
    .SYNOPSIS
        Safely gets a property from an object (hashtable or PSObject).
    #>
    param($Object, [string]$PropertyName)

    if ($null -eq $Object) { return $null }

    if ($Object -is [hashtable]) {
        if ($Object.ContainsKey($PropertyName)) {
            return $Object[$PropertyName]
        }
    }
    elseif ($Object.PSObject.Properties.Name -contains $PropertyName) {
        return $Object.$PropertyName
    }

    return $null
}

function Invoke-ChecksQuery {
    <#
    .SYNOPSIS
        Executes the GraphQL query and returns parsed result.
    #>
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$Number
    )

    $result = gh api graphql -f query=$query -f owner="$Owner" -f repo="$Repo" -F number=$Number 2>&1

    if ($LASTEXITCODE -ne 0) {
        $resultStr = [string]$result
        if ($resultStr -match 'Could not resolve to a PullRequest' -or $resultStr -match 'not found') {
            return @{ Error = "NotFound"; Message = "PR #$Number not found in $Owner/$Repo" }
        }
        return @{ Error = "ApiError"; Message = "GraphQL query failed: $resultStr" }
    }

    try {
        return $result | ConvertFrom-Json
    }
    catch {
        return @{ Error = "ApiError"; Message = "Failed to parse GraphQL response: $_" }
    }
}

function ConvertTo-CheckInfo {
    <#
    .SYNOPSIS
        Converts a GraphQL context node to a normalized check info object.
    #>
    param($Context)

    if ($null -eq $Context) { return $null }

    $typeName = Get-SafeProperty $Context '__typename'

    if ($typeName -eq 'CheckRun') {
        # GitHub Actions / Check Runs
        $status = Get-SafeProperty $Context 'status'
        $conclusion = Get-SafeProperty $Context 'conclusion'

        return [PSCustomObject]@{
            Name       = Get-SafeProperty $Context 'name'
            Type       = 'CheckRun'
            State      = $status
            Conclusion = $conclusion
            DetailsUrl = Get-SafeProperty $Context 'detailsUrl'
            IsRequired = Get-SafeProperty $Context 'isRequired'
            IsPending  = $status -in @('QUEUED', 'IN_PROGRESS', 'WAITING', 'PENDING', 'REQUESTED')
            IsPassing  = $conclusion -in @('SUCCESS', 'NEUTRAL', 'SKIPPED')
            IsFailing  = $conclusion -in @('FAILURE', 'CANCELLED', 'TIMED_OUT', 'ACTION_REQUIRED')
        }
    }
    elseif ($typeName -eq 'StatusContext') {
        # Legacy Status API
        $state = Get-SafeProperty $Context 'state'

        return [PSCustomObject]@{
            Name       = Get-SafeProperty $Context 'context'
            Type       = 'StatusContext'
            State      = $state
            Conclusion = $state  # For StatusContext, state IS the conclusion
            DetailsUrl = Get-SafeProperty $Context 'targetUrl'
            IsRequired = Get-SafeProperty $Context 'isRequired'
            IsPending  = $state -in @('PENDING', 'EXPECTED')
            IsPassing  = $state -eq 'SUCCESS'
            IsFailing  = $state -in @('FAILURE', 'ERROR')
        }
    }

    return $null
}

function Get-ChecksFromResponse {
    <#
    .SYNOPSIS
        Extracts and normalizes checks from GraphQL response.
    #>
    param($Response, [switch]$RequiredOnly)

    $pr = Get-SafeProperty (Get-SafeProperty $Response 'data') 'repository'
    $pr = Get-SafeProperty $pr 'pullRequest'

    if (-not $pr) {
        return @{ Error = "NotFound"; Message = "PR not found in response" }
    }

    $commits = Get-SafeProperty $pr 'commits'
    $nodes = @(Get-SafeProperty $commits 'nodes')

    if (-not $nodes -or $nodes.Count -eq 0) {
        return @{
            Number       = Get-SafeProperty $pr 'number'
            Checks       = @()
            OverallState = 'UNKNOWN'
            HasChecks    = $false
        }
    }

    $commit = Get-SafeProperty $nodes[0] 'commit'
    $rollup = Get-SafeProperty $commit 'statusCheckRollup'

    if (-not $rollup) {
        return @{
            Number       = Get-SafeProperty $pr 'number'
            Checks       = @()
            OverallState = 'UNKNOWN'
            HasChecks    = $false
        }
    }

    $overallState = Get-SafeProperty $rollup 'state'
    $contexts = Get-SafeProperty $rollup 'contexts'
    $contextNodes = @(Get-SafeProperty $contexts 'nodes')

    $checks = @()
    if ($contextNodes) {
        foreach ($ctx in $contextNodes) {
            $check = ConvertTo-CheckInfo -Context $ctx
            if ($check) {
                if ($RequiredOnly -and -not $check.IsRequired) {
                    continue
                }
                $checks += $check
            }
        }
    }

    return @{
        Number       = Get-SafeProperty $pr 'number'
        Checks       = $checks
        OverallState = $overallState
        HasChecks    = $true
    }
}

#endregion

#region Main Logic

function Get-PRChecksOnce {
    <#
    .SYNOPSIS
        Fetches PR checks once and returns result object.
    #>
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$Number,
        [switch]$RequiredOnly
    )

    $response = Invoke-ChecksQuery -Owner $Owner -Repo $Repo -Number $Number

    if ($response.Error) {
        return $response
    }

    return Get-ChecksFromResponse -Response $response -RequiredOnly:$RequiredOnly
}

function Build-Output {
    <#
    .SYNOPSIS
        Builds the final output object from check data.
    #>
    param($CheckData, [string]$Owner, [string]$Repo)

    $checks = $CheckData.Checks
    $failedCount = @($checks | Where-Object { $_.IsFailing }).Count
    $pendingCount = @($checks | Where-Object { $_.IsPending }).Count
    $passedCount = @($checks | Where-Object { $_.IsPassing }).Count

    # AllPassing: true only if there are checks and none are failing or pending
    $allPassing = $CheckData.HasChecks -and ($checks.Count -gt 0) -and ($failedCount -eq 0) -and ($pendingCount -eq 0)

    return [PSCustomObject]@{
        Success      = $true
        Number       = $CheckData.Number
        Owner        = $Owner
        Repo         = $Repo
        OverallState = $CheckData.OverallState
        HasChecks    = $CheckData.HasChecks
        Checks       = @($checks | ForEach-Object {
            [PSCustomObject]@{
                Name       = $_.Name
                State      = $_.State
                Conclusion = $_.Conclusion
                DetailsUrl = $_.DetailsUrl
                IsRequired = $_.IsRequired
            }
        })
        FailedCount  = $failedCount
        PendingCount = $pendingCount
        PassedCount  = $passedCount
        AllPassing   = $allPassing
    }
}

# Only execute when invoked directly (not dot-sourced for testing)
# When dot-sourced, the helper functions above are available but main logic is skipped
if ($MyInvocation.InvocationName -eq '.') {
    return
}

# Verify authentication and resolve parameters
Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

# Execute the check
Write-Verbose "Fetching CI checks for PR #$PullRequest from $Owner/$Repo"

$startTime = Get-Date
$iteration = 0
$maxIterations = [math]::Ceiling($TimeoutSeconds / 10)  # Poll every 10 seconds

do {
    $iteration++
    $checkData = Get-PRChecksOnce -Owner $Owner -Repo $Repo -Number $PullRequest -RequiredOnly:$RequiredOnly

    # Handle errors
    if ($checkData.Error -eq 'NotFound') {
        $output = [PSCustomObject]@{
            Success = $false
            Error   = $checkData.Message
            Number  = $PullRequest
        }
        Write-Output ($output | ConvertTo-Json -Depth 10)
        exit 2
    }

    if ($checkData.Error -eq 'ApiError') {
        $output = [PSCustomObject]@{
            Success = $false
            Error   = $checkData.Message
            Number  = $PullRequest
        }
        Write-Output ($output | ConvertTo-Json -Depth 10)
        exit 3
    }

    $output = Build-Output -CheckData $checkData -Owner $Owner -Repo $Repo

    # If not waiting, or if no pending checks, we're done
    if (-not $Wait -or $output.PendingCount -eq 0) {
        break
    }

    # Check timeout
    $elapsed = (Get-Date) - $startTime
    if ($elapsed.TotalSeconds -ge $TimeoutSeconds) {
        Write-Verbose "Timeout reached after $($elapsed.TotalSeconds) seconds"
        Write-Output ($output | ConvertTo-Json -Depth 10)
        Write-Host "Timeout: $($output.PendingCount) checks still pending after $TimeoutSeconds seconds" -ForegroundColor Yellow
        exit 7
    }

    # Wait before next poll
    Write-Verbose "Iteration $iteration`: $($output.PendingCount) pending, $($output.PassedCount) passed, $($output.FailedCount) failed. Waiting 10s..."
    Start-Sleep -Seconds 10

} while ($iteration -lt $maxIterations)

# Output result
Write-Output ($output | ConvertTo-Json -Depth 10)

# Determine exit code
if ($output.FailedCount -gt 0) {
    Write-Host "PR #$($output.Number): $($output.FailedCount) check(s) failed" -ForegroundColor Red
    exit 1
}
elseif ($output.PendingCount -gt 0) {
    Write-Host "PR #$($output.Number): $($output.PendingCount) check(s) still pending" -ForegroundColor Yellow
    exit 0  # Pending is not failure
}
else {
    Write-Host "PR #$($output.Number): All $($output.PassedCount) check(s) passing" -ForegroundColor Green
    exit 0
}

#endregion
