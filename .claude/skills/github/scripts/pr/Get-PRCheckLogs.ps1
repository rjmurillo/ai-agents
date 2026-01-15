<#
.SYNOPSIS
    Fetches logs from failing GitHub Actions checks on a Pull Request.

.DESCRIPTION
    Retrieves failure logs from GitHub Actions workflow runs associated with
    failing PR checks. Extracts relevant failure snippets with configurable
    context for debugging.

    Supports two modes:
    1. Standalone: Provide -PullRequest to fetch checks and logs in one call
    2. Pipeline: Pipe output from Get-PRChecks.ps1 to fetch logs for failures

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER PullRequest
    PR number. Required in standalone mode.

.PARAMETER ChecksInput
    JSON string from Get-PRChecks.ps1 output. Used in pipeline mode.

.PARAMETER MaxLines
    Maximum lines to extract per failure snippet. Default: 160.

.PARAMETER ContextLines
    Lines of context before and after failure markers. Default: 30.

.EXAMPLE
    .\Get-PRCheckLogs.ps1 -PullRequest 123

.EXAMPLE
    .\Get-PRChecks.ps1 -PullRequest 123 | .\Get-PRCheckLogs.ps1

.EXAMPLE
    .\Get-PRCheckLogs.ps1 -PullRequest 123 -MaxLines 200 -ContextLines 50

.NOTES
    Exit Codes:
      0 - Success (logs retrieved, or no failing checks)
      1 - Invalid parameters
      2 - PR not found
      3 - API error
      4 - Authentication error

    Only processes GitHub Actions checks (CheckRun type with github.com URLs).
    External CI systems (Buildkite, CircleCI, etc.) are noted but not fetched.

    See: ADR-035 Exit Code Standardization
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [int]$PullRequest,
    [Parameter(ValueFromPipeline)]
    [string]$ChecksInput,
    [int]$MaxLines = 160,
    [int]$ContextLines = 30
)

$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubCore.psm1") -Force

#region Failure Detection Patterns

# Patterns that indicate failure in log output
$script:FailurePatterns = @(
    '(?i)\berror\b',
    '(?i)\bfail(ed|ure|ing)?\b',
    '(?i)\btraceback\b',
    '(?i)\bexception\b',
    '(?i)\bpanic\b',
    '(?i)\bfatal\b',
    '(?i)\btimeout\b',
    '(?i)\bERROR:',
    '(?i)##\[error\]',
    '(?i)Process completed with exit code [1-9]',
    '(?i)\bsegmentation fault\b',
    '(?i)\bstack trace\b',
    '(?i)\bassertion failed\b'
)

$script:CombinedPattern = $script:FailurePatterns -join '|'

#endregion

#region Helper Functions

function Get-RunIdFromUrl {
    <#
    .SYNOPSIS
        Extracts workflow run ID from a GitHub Actions URL.
    #>
    param([string]$Url)

    # Pattern: https://github.com/owner/repo/actions/runs/12345678/job/12345
    # Or: https://github.com/owner/repo/actions/runs/12345678
    if ($Url -match '/actions/runs/(\d+)') {
        return $Matches[1]
    }
    return $null
}

function Get-JobIdFromUrl {
    <#
    .SYNOPSIS
        Extracts job ID from a GitHub Actions URL.
    #>
    param([string]$Url)

    # Pattern: https://github.com/owner/repo/actions/runs/12345678/job/12345
    if ($Url -match '/job/(\d+)') {
        return $Matches[1]
    }
    return $null
}

function Test-IsGitHubActionsUrl {
    <#
    .SYNOPSIS
        Checks if URL points to GitHub Actions.
    #>
    param([string]$Url)

    return $Url -match 'github\.com/.+/actions/runs/'
}

function Get-FailureSnippets {
    <#
    .SYNOPSIS
        Extracts failure snippets from log content with context.
    #>
    param(
        [string[]]$LogLines,
        [int]$ContextLines,
        [int]$MaxLines
    )

    $snippets = [System.Collections.Generic.List[object]]::new()
    $totalExtracted = 0

    for ($i = 0; $i -lt $LogLines.Count -and $totalExtracted -lt $MaxLines; $i++) {
        $line = $LogLines[$i]

        if ($line -match $script:CombinedPattern) {
            # Calculate context bounds
            $start = [Math]::Max(0, $i - $ContextLines)
            $end = [Math]::Min($LogLines.Count - 1, $i + $ContextLines)

            # Extract snippet
            $snippetLines = $LogLines[$start..$end]
            $linesAvailable = $MaxLines - $totalExtracted
            if ($snippetLines.Count -gt $linesAvailable) {
                $snippetLines = $snippetLines[0..($linesAvailable - 1)]
            }

            $snippets.Add(@{
                LineNumber    = $i + 1
                MatchedLine   = $line.Trim()
                Context       = $snippetLines -join "`n"
                StartLine     = $start + 1
                # EndLine is 1-based and inclusive of the final snippet line.
                EndLine       = $start + $snippetLines.Count
            })

            $totalExtracted += $snippetLines.Count

            # Skip ahead to avoid overlapping snippets
            $i = $end
        }
    }

    return @($snippets)
}

function Get-WorkflowRunLogs {
    <#
    .SYNOPSIS
        Fetches logs for a GitHub Actions workflow run.
    #>
    param(
        [string]$Owner,
        [string]$Repo,
        [string]$RunId,
        [string]$JobId
    )

    # Try job-specific logs first if we have a job ID
    if ($JobId) {
        Write-Verbose "Fetching logs for job $JobId in run $RunId"

        # Get job logs via API
        $result = gh api "repos/$Owner/$Repo/actions/jobs/$JobId/logs" 2>&1

        if ($LASTEXITCODE -eq 0 -and $result) {
            return @{
                Success = $true
                Content = $result
                Source  = "job"
            }
        }
    }

    # Fall back to run view which gives formatted output
    Write-Verbose "Fetching logs for run $RunId via gh run view"

    $result = gh run view "$RunId" --repo "$Owner/$Repo" --log-failed 2>&1

    if ($LASTEXITCODE -eq 0 -and $result) {
        return @{
            Success = $true
            Content = $result
            Source  = "run-failed"
        }
    }

    # Try full log if --log-failed didn't work
    $result = gh run view "$RunId" --repo "$Owner/$Repo" --log 2>&1

    if ($LASTEXITCODE -eq 0 -and $result) {
        return @{
            Success = $true
            Content = $result
            Source  = "run-full"
        }
    }

    return @{
        Success = $false
        Error   = "Failed to fetch logs: $result"
        Source  = "none"
    }
}

#endregion

#region Main Logic

function Get-CheckLogs {
    <#
    .SYNOPSIS
        Main function to fetch logs for failing checks.
    #>
    param(
        [string]$Owner,
        [string]$Repo,
        [array]$FailingChecks,
        [int]$MaxLines,
        [int]$ContextLines
    )

    $results = [System.Collections.Generic.List[object]]::new()

    foreach ($check in $FailingChecks) {
        $checkResult = @{
            Name       = $check.Name
            DetailsUrl = $check.DetailsUrl
            State      = $check.State
            Conclusion = $check.Conclusion
        }

        # Check if this is a GitHub Actions URL
        if (-not (Test-IsGitHubActionsUrl $check.DetailsUrl)) {
            $checkResult['LogSource'] = 'external'
            $checkResult['Note'] = 'External CI system - logs not accessible via GitHub API'
            $checkResult['Snippets'] = @()
            $results.Add($checkResult)
            continue
        }

        # Extract run and job IDs
        $runId = Get-RunIdFromUrl $check.DetailsUrl
        $jobId = Get-JobIdFromUrl $check.DetailsUrl

        if (-not $runId) {
            $checkResult['LogSource'] = 'error'
            $checkResult['Error'] = 'Could not extract run ID from URL'
            $checkResult['Snippets'] = @()
            $results.Add($checkResult)
            continue
        }

        $checkResult['RunId'] = $runId
        if ($jobId) { $checkResult['JobId'] = $jobId }

        # Fetch logs
        $logResult = Get-WorkflowRunLogs -Owner $Owner -Repo $Repo -RunId $runId -JobId $jobId

        if (-not $logResult.Success) {
            $checkResult['LogSource'] = 'error'
            $checkResult['Error'] = $logResult.Error
            $checkResult['Snippets'] = @()
            $results.Add($checkResult)
            continue
        }

        $checkResult['LogSource'] = $logResult.Source

        # Parse logs and extract failure snippets
        $logContent = $logResult.Content
        if ($logContent -is [array]) {
            $logLines = $logContent
        }
        else {
            $logLines = $logContent -split "`n"
        }

        $snippets = Get-FailureSnippets -LogLines $logLines -ContextLines $ContextLines -MaxLines $MaxLines
        $checkResult['Snippets'] = $snippets
        $checkResult['TotalLogLines'] = $logLines.Count

        $results.Add($checkResult)
    }

    return @($results)
}

# Skip main execution when dot-sourced for testing
if ($MyInvocation.InvocationName -eq '.') {
    return
}

# Verify authentication
try {
    Assert-GhAuthenticated
}
catch {
    $output = [PSCustomObject]@{
        Success = $false
        Error   = "Authentication failed: $_"
    }
    Write-Output ($output | ConvertTo-Json -Depth 10)
    exit 4
}

# Resolve repository parameters
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

# Get failing checks - either from input or by fetching
$failingChecks = @()

if ($ChecksInput) {
    # Pipeline mode - parse input from Get-PRChecks
    try {
        $checksData = $ChecksInput | ConvertFrom-Json

        if (-not $checksData.Success) {
            $output = [PSCustomObject]@{
                Success = $false
                Error   = "Input checks data indicates failure: $($checksData.Error)"
            }
            Write-Output ($output | ConvertTo-Json -Depth 10)
            exit 1
        }

        $failingChecks = @($checksData.Checks | Where-Object {
            $_.Conclusion -in @('FAILURE', 'CANCELLED', 'TIMED_OUT', 'ACTION_REQUIRED')
        })
    }
    catch {
        $output = [PSCustomObject]@{
            Success = $false
            Error   = "Failed to parse checks input: $_"
        }
        Write-Output ($output | ConvertTo-Json -Depth 10)
        exit 1
    }
}
elseif ($PullRequest -gt 0) {
    # Standalone mode - fetch checks first
    Write-Verbose "Fetching checks for PR #$PullRequest"

    $checksScript = Join-Path $PSScriptRoot "Get-PRChecks.ps1"
    $checksJson = & $checksScript -Owner $Owner -Repo $Repo -PullRequest $PullRequest

    if ($LASTEXITCODE -ne 0) {
        Write-Output $checksJson
        exit $LASTEXITCODE
    }

    try {
        $checksData = $checksJson | ConvertFrom-Json

        if (-not $checksData.Success) {
            Write-Output $checksJson
            exit 2
        }

        $failingChecks = @($checksData.Checks | Where-Object {
            $_.Conclusion -in @('FAILURE', 'CANCELLED', 'TIMED_OUT', 'ACTION_REQUIRED')
        })
    }
    catch {
        $output = [PSCustomObject]@{
            Success = $false
            Error   = "Failed to parse checks response: $_"
        }
        Write-Output ($output | ConvertTo-Json -Depth 10)
        exit 3
    }
}
else {
    $output = [PSCustomObject]@{
        Success = $false
        Error   = "Either -PullRequest or pipeline input from Get-PRChecks is required"
    }
    Write-Output ($output | ConvertTo-Json -Depth 10)
    exit 1
}

# If no failing checks, return success with empty results
if ($failingChecks.Count -eq 0) {
    $output = [PSCustomObject]@{
        Success        = $true
        Owner          = $Owner
        Repo           = $Repo
        PullRequest    = $PullRequest
        FailingChecks  = 0
        Message        = "No failing checks found"
        CheckLogs      = @()
    }
    Write-Output ($output | ConvertTo-Json -Depth 10)
    Write-Host "No failing checks to analyze" -ForegroundColor Green
    exit 0
}

# Fetch logs for failing checks
Write-Verbose "Analyzing $($failingChecks.Count) failing check(s)"

$checkLogs = Get-CheckLogs -Owner $Owner -Repo $Repo -FailingChecks $failingChecks -MaxLines $MaxLines -ContextLines $ContextLines

# Build output
$output = [PSCustomObject]@{
    Success       = $true
    Owner         = $Owner
    Repo          = $Repo
    PullRequest   = $PullRequest
    FailingChecks = $failingChecks.Count
    CheckLogs     = $checkLogs
}

Write-Output ($output | ConvertTo-Json -Depth 15)

# Summary message
$logsFound = @($checkLogs | Where-Object { $_.Snippets.Count -gt 0 }).Count
$external = @($checkLogs | Where-Object { $_.LogSource -eq 'external' }).Count

if ($external -gt 0) {
    Write-Host "Analyzed $($failingChecks.Count) failing check(s): $logsFound with logs, $external external (logs not accessible)" -ForegroundColor Yellow
}
else {
    Write-Host "Analyzed $($failingChecks.Count) failing check(s) with $logsFound containing failure snippets" -ForegroundColor Cyan
}

exit 0

#endregion
