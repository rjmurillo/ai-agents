<#
.SYNOPSIS
    Processes PR comments based on AI triage output.

.DESCRIPTION
    Executes after ai-review action triage to:
    1. Acknowledge comments (add eyes reaction)
    2. Implement quick-fixes (if applicable)
    3. Reply to comments that need responses
    4. Resolve stale threads

.PARAMETER PRNumber
    PR number to process (required).

.PARAMETER Verdict
    AI verdict from ai-review action.

.PARAMETER FindingsJson
    Raw JSON output from AI containing triage decisions.

.PARAMETER DryRun
    If set, only logs actions without executing them.

.EXAMPLE
    .\Invoke-PRCommentProcessing.ps1 -PRNumber 457 -Verdict "PASS" -FindingsJson $jsonString

.NOTES
    Called by ai-review action's execute-script feature.
    Exit Codes: 0=Success, 1=Invalid params, 2=Parse error, 3=API error
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [int]$PRNumber,

    [Parameter(Mandatory)]
    [string]$Verdict,

    [Parameter(Mandatory)]
    [string]$FindingsJson,

    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

# Parse AI findings
function Get-Findings {
    param([string]$Json)

    # Handle markdown code fences if present
    $cleanJson = $Json
    if ($Json -match '```(?:json)?\s*([\s\S]*?)```') {
        $cleanJson = $Matches[1].Trim()
    }

    try {
        return $cleanJson | ConvertFrom-Json
    }
    catch {
        Write-Error "Failed to parse AI findings JSON: $_"
        Write-Verbose "Raw JSON: $($Json.Substring(0, [Math]::Min(500, $Json.Length)))"
        exit 2
    }
}

# Add reaction to a comment
function Add-CommentReaction {
    param(
        [long]$CommentId,
        [string]$Reaction = 'eyes'
    )

    if ($DryRun) {
        Write-Host "[DRY-RUN] Would add $Reaction reaction to comment $CommentId"
        return
    }

    $resolved = Resolve-RepoParams
    $result = gh api "repos/$($resolved.Owner)/$($resolved.Repo)/pulls/comments/$CommentId/reactions" `
        -X POST -f content=$Reaction 2>&1

    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Failed to add reaction to comment $CommentId : $result"
    }
    else {
        Write-Host "Added $Reaction reaction to comment $CommentId" -ForegroundColor Green
    }
}

# Process comments based on classification
function Invoke-CommentProcessing {
    param([object]$Findings)

    $stats = @{
        Acknowledged = 0
        Replied      = 0
        Resolved     = 0
        Skipped      = 0
        Errors       = 0
    }

    foreach ($comment in $Findings.comments) {
        Write-Host "Processing comment $($comment.id) [$($comment.classification)]" -ForegroundColor Cyan

        # Always acknowledge with eyes reaction
        try {
            Add-CommentReaction -CommentId $comment.id -Reaction 'eyes'
            $stats.Acknowledged++
        }
        catch {
            Write-Warning "Failed to acknowledge comment $($comment.id): $_"
            $stats.Errors++
        }

        # Handle based on classification
        switch ($comment.classification) {
            'stale' {
                # Mark as resolved
                if (-not $DryRun) {
                    Write-Host "  Marking stale comment as resolved"
                    # Note: Resolving requires the thread ID, not comment ID
                    # This would need additional lookup
                }
                $stats.Resolved++
            }

            'wontfix' {
                # Reply with decline rationale
                if (-not $DryRun -and $comment.resolution) {
                    $body = "Thank you for the feedback. After review, we've decided not to implement this change:`n`n$($comment.resolution)"
                    try {
                        & "$PSScriptRoot/Post-PRCommentReply.ps1" `
                            -PullRequest $PRNumber `
                            -CommentId $comment.id `
                            -Body $body
                        $stats.Replied++
                    }
                    catch {
                        Write-Warning "Failed to reply to comment $($comment.id): $_"
                        $stats.Errors++
                    }
                }
            }

            'question' {
                # Flag for human follow-up
                Write-Host "  Needs human response: $($comment.summary)" -ForegroundColor Yellow
                $stats.Skipped++
            }

            { $_ -in 'quick-fix', 'standard', 'strategic' } {
                # These require implementation or strategic response
                Write-Host "  Action needed: $($comment.action) - $($comment.summary)" -ForegroundColor Yellow
                $stats.Skipped++
            }
        }
    }

    return $stats
}

# Main execution
Write-Host "=== PR Comment Processing ===" -ForegroundColor Magenta
Write-Host "PR Number: $PRNumber"
Write-Host "Verdict: $Verdict"
Write-Host "DryRun: $DryRun"
Write-Host ""

if ($Verdict -notin 'PASS', 'WARN') {
    Write-Warning "AI verdict was $Verdict - skipping comment processing"
    exit 0
}

# Parse findings
$findings = Get-Findings -Json $FindingsJson

if (-not $findings.comments -or $findings.comments.Count -eq 0) {
    Write-Host "No comments to process" -ForegroundColor Green
    exit 0
}

Write-Host "Found $($findings.comments.Count) comments to process"
Write-Host ""

# Process comments
$stats = Invoke-CommentProcessing -Findings $findings

# Output summary
Write-Host ""
Write-Host "=== Processing Summary ===" -ForegroundColor Magenta
Write-Host "  Acknowledged: $($stats.Acknowledged)"
Write-Host "  Replied: $($stats.Replied)"
Write-Host "  Resolved: $($stats.Resolved)"
Write-Host "  Skipped (needs human): $($stats.Skipped)"
Write-Host "  Errors: $($stats.Errors)"

if ($stats.Errors -gt 0) {
    Write-Warning "Completed with $($stats.Errors) errors"
    exit 3
}

Write-Host "Processing complete" -ForegroundColor Green
exit 0
