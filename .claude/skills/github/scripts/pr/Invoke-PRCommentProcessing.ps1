#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Processes PR comments based on AI triage analysis.

.DESCRIPTION
    Executes post-analysis actions on PR comments:
    1. Acknowledges all comments (adds eyes reaction)
    2. Resolves threads that are marked for resolution
    3. Outputs processing summary

    Designed to be called by the ai-review action's execute-script feature
    after Copilot CLI has analyzed and triaged the PR comments.

    See: .github/prompts/pr-comment-triage.md for expected JSON format

.PARAMETER PRNumber
    Pull request number (required).

.PARAMETER Verdict
    AI review verdict (PASS, WARN, CRITICAL_FAIL).

.PARAMETER FindingsJson
    JSON string containing the triage results from Copilot CLI.
    Expected format:
    {
      "comments": [
        {
          "id": 123456789,
          "thread_id": "PRRT_abc123",
          "author": "coderabbitai[bot]",
          "classification": "quick-fix",
          "priority": "major",
          "action": "implement",
          "summary": "Add error handling"
        }
      ],
      "total_comments": 5,
      "actionable_count": 3
    }

.EXAMPLE
    ./Invoke-PRCommentProcessing.ps1 -PRNumber 453 -Verdict "PASS" -FindingsJson '{"comments":[]}'

.NOTES
    Exit Codes:
    - 0: Success
    - 1: Invalid parameters
    - 2: JSON parsing error
    - 3: API error during processing
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [int]$PRNumber,

    [Parameter()]
    [string]$Verdict = 'PASS',

    [Parameter()]
    [string]$FindingsJson = '{}'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

#region Helpers

function Get-RepoInfo {
    [CmdletBinding()]
    param()
    $remote = git remote get-url origin 2>$null
    if (-not $remote) {
        throw "Not in a git repository or no origin remote"
    }

    if ($remote -match 'github\.com[:/]([^/]+)/([^/.]+)') {
        return @{
            Owner = $Matches[1]
            Repo = $Matches[2] -replace '\.git$', ''
        }
    }

    throw "Could not parse GitHub repository from remote: $remote"
}

function Add-EyesReaction {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [long]$CommentId
    )

    $scriptDir = $PSScriptRoot
    $reactScript = Join-Path $scriptDir '..' 'reactions' 'Add-CommentReaction.ps1'

    if (-not (Test-Path $reactScript)) {
        Write-Warning "Add-CommentReaction.ps1 not found at $reactScript"
        return $false
    }

    try {
        & $reactScript -CommentId $CommentId -Reaction 'eyes' -ErrorAction SilentlyContinue
        return $LASTEXITCODE -eq 0
    }
    catch {
        Write-Warning "Failed to add eyes reaction to comment $CommentId: $_"
        return $false
    }
}

function Resolve-Thread {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$ThreadId
    )

    $scriptDir = $PSScriptRoot
    $resolveScript = Join-Path $scriptDir 'Resolve-PRReviewThread.ps1'

    if (-not (Test-Path $resolveScript)) {
        Write-Warning "Resolve-PRReviewThread.ps1 not found at $resolveScript"
        return $false
    }

    try {
        & $resolveScript -ThreadId $ThreadId -ErrorAction SilentlyContinue
        return $LASTEXITCODE -eq 0
    }
    catch {
        Write-Warning "Failed to resolve thread $ThreadId: $_"
        return $false
    }
}

#endregion

#region Main Logic

function Invoke-PRCommentProcessing {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [int]$PR,

        [Parameter()]
        [string]$Verdict,

        [Parameter()]
        [string]$FindingsJson
    )

    $result = [PSCustomObject]@{
        Success = $false
        PRNumber = $PR
        Verdict = $Verdict
        TotalComments = 0
        AcknowledgedCount = 0
        ResolvedCount = 0
        FailedCount = 0
        Message = ''
    }

    # Parse findings JSON
    try {
        $findings = $FindingsJson | ConvertFrom-Json
    }
    catch {
        $result.Message = "Failed to parse findings JSON: $_"
        Write-Warning $result.Message
        return $result
    }

    # Handle case where JSON doesn't contain expected structure
    if ($null -eq $findings.comments) {
        # Try to extract JSON from raw output (Copilot may include prose around the JSON)
        if ($FindingsJson -match '\{[\s\S]*"comments"[\s\S]*\}') {
            $jsonMatch = $Matches[0]
            try {
                $findings = $jsonMatch | ConvertFrom-Json
            }
            catch {
                $result.Message = "Could not extract valid JSON from findings"
                Write-Warning $result.Message
                return $result
            }
        }
        else {
            $result.Message = "Findings JSON does not contain comments array"
            Write-Warning $result.Message
            # Not an error - may just be no comments to process
            $result.Success = $true
            return $result
        }
    }

    $comments = @($findings.comments)
    $result.TotalComments = $comments.Count

    Write-Host "Processing $($comments.Count) comments for PR #$PR" -ForegroundColor Cyan

    foreach ($comment in $comments) {
        # Skip comments that should be deferred
        if ($comment.action -eq 'defer') {
            Write-Host "  Skipping deferred comment $($comment.id)" -ForegroundColor Yellow
            continue
        }

        # Acknowledge comment with eyes reaction
        if ($comment.id) {
            $acknowledged = Add-EyesReaction -CommentId $comment.id
            if ($acknowledged) {
                $result.AcknowledgedCount++
                Write-Host "  Acknowledged comment $($comment.id) ($($comment.summary))" -ForegroundColor Green
            }
            else {
                $result.FailedCount++
                Write-Host "  Failed to acknowledge comment $($comment.id)" -ForegroundColor Red
            }
        }

        # Resolve thread if action indicates it should be resolved
        if ($comment.action -eq 'resolve' -and $comment.thread_id) {
            $resolved = Resolve-Thread -ThreadId $comment.thread_id
            if ($resolved) {
                $result.ResolvedCount++
                Write-Host "  Resolved thread $($comment.thread_id)" -ForegroundColor Green
            }
            else {
                Write-Host "  Could not resolve thread $($comment.thread_id)" -ForegroundColor Yellow
            }
        }
    }

    $result.Success = $result.FailedCount -eq 0
    $result.Message = "Processed $($result.TotalComments) comments: $($result.AcknowledgedCount) acknowledged, $($result.ResolvedCount) resolved, $($result.FailedCount) failed"

    Write-Host ""
    Write-Host "Summary: $($result.Message)" -ForegroundColor $(if ($result.Success) { 'Green' } else { 'Yellow' })

    return $result
}

#endregion

#region Entry Point

# Guard: Only execute main logic when run directly, not when dot-sourced for testing
if ($MyInvocation.InvocationName -eq '.') {
    return
}

Write-Host "=== PR Comment Processing ===" -ForegroundColor Cyan
Write-Host "PR: #$PRNumber"
Write-Host "Verdict: $Verdict"
Write-Host ""

$result = Invoke-PRCommentProcessing -PR $PRNumber -Verdict $Verdict -FindingsJson $FindingsJson

# Output result as JSON
$result | ConvertTo-Json -Depth 5

# Exit with appropriate code
if ($result.Success) {
    exit 0
}
else {
    exit 3
}

#endregion
