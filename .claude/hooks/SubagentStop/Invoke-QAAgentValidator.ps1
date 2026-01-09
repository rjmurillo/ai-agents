<#
.SYNOPSIS
    Validates QA agent output completeness when qa subagent stops.

.DESCRIPTION
    Claude Code SubagentStop hook that verifies QA validation reports are
    complete and contain required sections. This ensures quality gates are
    properly executed per SESSION-PROTOCOL requirements.

    Part of the hooks expansion implementation (Issue #773, Phase 2).

.NOTES
    Hook Type: SubagentStop
    Exit Codes:
        0 = Success, validation result in stdout
        Other = Warning (non-blocking)

.LINK
    .agents/SESSION-PROTOCOL.md
    .agents/analysis/claude-code-hooks-opportunity-analysis.md
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'  # Non-blocking validation

try {
    # Parse hook input from stdin (JSON)
    $hookInput = $null
    if (-not [Console]::IsInputRedirected) {
        # No input, allow stop
        exit 0
    }

    $inputJson = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($inputJson)) {
        exit 0
    }

    $hookInput = $inputJson | ConvertFrom-Json -ErrorAction Stop

    # Check if this is a qa agent (subagent_type)
    $isQAAgent = $false
    if ($hookInput.PSObject.Properties['subagent_type']) {
        $subagentType = $hookInput.subagent_type
        if ($subagentType -eq 'qa') {
            $isQAAgent = $true
        }
    }

    if (-not $isQAAgent) {
        # Not a QA agent, allow stop
        exit 0
    }

    # Get transcript path to analyze QA output
    $transcriptPath = $null
    if ($hookInput.PSObject.Properties['transcript_path']) {
        $transcriptPath = $hookInput.transcript_path
    }

    if ([string]::IsNullOrWhiteSpace($transcriptPath) -or -not (Test-Path $transcriptPath)) {
        # No transcript available, allow stop
        exit 0
    }

    # Read transcript and check for QA report indicators
    $transcript = Get-Content $transcriptPath -Raw -ErrorAction Stop

    # Check for required QA report sections
    $hasTestStrategy = $transcript -match 'Test Strategy|Testing Approach|Test Plan'
    $hasTestResults = $transcript -match 'Test Results|Validation Results|Test Execution'
    $hasCoverage = $transcript -match 'Coverage|Test Coverage|Acceptance Criteria'

    if (-not ($hasTestStrategy -and $hasTestResults -and $hasCoverage)) {
        # QA report incomplete - output warning (non-blocking for now)
        Write-Output "`n**QA Validation Warning**: QA agent report may be incomplete. Expected sections: Test Strategy, Test Results, Coverage Analysis.`n"
    }

    # Allow stop (non-blocking validation)
    exit 0
}
catch {
    # On error, allow stop (fail open)
    Write-Warning "QA agent validation failed: $($_.Exception.Message)"
    exit 0
}
