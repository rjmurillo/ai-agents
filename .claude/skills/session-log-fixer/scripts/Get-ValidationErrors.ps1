#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Extract validation errors from GitHub Actions Job Summary

.DESCRIPTION
    Reads the Job Summary from a failed Session Protocol Validation workflow run
    and extracts the specific validation errors to guide fixes.

.PARAMETER RunId
    The GitHub Actions run ID to fetch errors from

.PARAMETER PullRequest
    The pull request number (will find latest failing run for the PR branch)

.OUTPUTS
    PSCustomObject with validation error details

.EXAMPLE
    & .claude/skills/session-log-fixer/scripts/Get-ValidationErrors.ps1 -RunId 20548622722

.EXAMPLE
    & .claude/skills/session-log-fixer/scripts/Get-ValidationErrors.ps1 -PullRequest 799

.NOTES
    Exit Codes:
    - 0: Success (errors extracted)
    - 1: Run not found or gh command failed
    - 2: No validation errors found in Job Summary

    Requires: gh CLI authenticated
#>

[CmdletBinding(DefaultParameterSetName='RunId')]
param(
    [Parameter(ParameterSetName='RunId', Mandatory)]
    [string]$RunId,

    [Parameter(ParameterSetName='PR', Mandatory)]
    [int]$PullRequest
)

$ErrorActionPreference = 'Continue'

function Get-RunIdFromPR {
    param([int]$PRNumber)

    # Get branch for PR
    $prInfo = gh pr view $PRNumber --json headRefName | ConvertFrom-Json
    $branch = $prInfo.headRefName

    # Get latest run for branch with Session Protocol workflow
    $runs = gh run list --branch $branch --workflow "session-protocol-validation.yml" --limit 5 --json databaseId,conclusion | ConvertFrom-Json

    # Find first failed run
    $failedRun = $runs | Where-Object { $_.conclusion -eq 'failure' } | Select-Object -First 1

    if (-not $failedRun) {
        throw "No failed Session Protocol validation runs found for PR #$PRNumber"
    }

    return $failedRun.databaseId
}

function Parse-JobSummary {
    param([string]$Summary)

    $result = @{
        OverallVerdict = $null
        MustFailureCount = 0
        NonCompliantSessions = @()
        DetailedErrors = @{}
    }

    # Extract overall verdict
    if ($Summary -match 'Overall Verdict:\s*\*\*([A-Z_]+)\*\*') {
        $result.OverallVerdict = $Matches[1]
    }

    # Extract MUST failure count
    if ($Summary -match '(\d+)\s+MUST requirement\(s\) not met') {
        $result.MustFailureCount = [int]$Matches[1]
    }

    # Extract non-compliant sessions from table
    $lines = $Summary -split "`n"
    $inTable = $false

    foreach ($line in $lines) {
        if ($line -match '^\|\s*Session File\s*\|') {
            $inTable = $true
            continue
        }

        if ($inTable) {
            if ($line -match '^\|\s*`([^`]+)`\s*\|\s*❌\s*NON_COMPLIANT\s*\|\s*(\d+)\s*\|') {
                $sessionFile = $Matches[1]
                $failCount = [int]$Matches[2]

                $result.NonCompliantSessions += @{
                    File = $sessionFile
                    MustFailures = $failCount
                }
            }
            elseif ($line -notmatch '^\|' -or $line -match '^---') {
                $inTable = $false
            }
        }

        # Extract detailed errors from expandable sections
        if ($line -match '<summary>📄\s*([^<]+)</summary>') {
            $currentSession = $Matches[1].Trim()
            $result.DetailedErrors[$currentSession] = @()
        }
        elseif ($line -match '^\|\s*([^|]+)\s*\|\s*MUST\s*\|\s*FAIL\s*\|\s*([^|]+)\s*\|') {
            $check = $Matches[1].Trim()
            $issue = $Matches[2].Trim()

            if ($currentSession) {
                $result.DetailedErrors[$currentSession] += @{
                    Check = $check
                    Issue = $issue
                }
            }
        }
    }

    return $result
}

# Resolve run ID
$targetRunId = if ($PullRequest) {
    try {
        Get-RunIdFromPR -PRNumber $PullRequest
    }
    catch {
        Write-Error "Failed to extract validation errors: $_"
        exit 1
    }
} else {
    $RunId
}

Write-Verbose "Fetching Job Summary for run $targetRunId"

# Fetch job summary using gh CLI
# The job summary is in the workflow run's jobs
try {
    $jobs = gh run view $targetRunId --json jobs 2>&1 | ConvertFrom-Json
}
catch {
    Write-Error "Failed to extract validation errors: Unable to fetch run details"
    exit 1
}

# Find the "Aggregate Results" job which contains the summary
$aggregateJob = $jobs.jobs | Where-Object { $_.name -match 'Aggregate Results' } | Select-Object -First 1

if (-not $aggregateJob) {
    Write-Error "No 'Aggregate Results' job found in run $targetRunId"
    exit 1
}

# Get the job log which includes the summary
try {
    $jobLog = gh run view $targetRunId --log-failed 2>&1
}
catch {
    Write-Error "Failed to extract validation errors: Unable to fetch job log"
    exit 1
}

# Parse the job summary from the log
# The summary is typically in the steps output
$parsedErrors = Parse-JobSummary -Summary $jobLog

if ($parsedErrors.NonCompliantSessions.Count -eq 0) {
    Write-Warning "No validation errors found in Job Summary for run $targetRunId"
    exit 2
}

# Output structured result
$output = [PSCustomObject]@{
    RunId = $targetRunId
    OverallVerdict = $parsedErrors.OverallVerdict
    MustFailureCount = $parsedErrors.MustFailureCount
    NonCompliantSessions = $parsedErrors.NonCompliantSessions
    DetailedErrors = $parsedErrors.DetailedErrors
}

$output | ConvertTo-Json -Depth 10
exit 0
