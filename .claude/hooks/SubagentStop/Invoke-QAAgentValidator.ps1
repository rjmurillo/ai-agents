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
        0 = Always (non-blocking hook, all errors are warnings)

.LINK
    .agents/SESSION-PROTOCOL.md
    .agents/analysis/claude-code-hooks-opportunity-analysis.md
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'  # Non-blocking validation

function Test-IsQAAgent {
    param($HookInput)

    if ($HookInput.PSObject.Properties['subagent_type']) {
        return $HookInput.subagent_type -eq 'qa'
    }
    return $false
}

function Get-TranscriptPath {
    param($HookInput)

    if ($HookInput.PSObject.Properties['transcript_path']) {
        $path = $HookInput.transcript_path
        if (-not [string]::IsNullOrWhiteSpace($path) -and (Test-Path $path)) {
            return $path
        }
    }
    return $null
}

function Get-MissingQASections {
    param([string]$Transcript)

    $missing = @()

    # Use more specific patterns that match actual section headers (markdown h1-h3)
    # to avoid false positives from keywords appearing elsewhere
    $hasTestStrategy = ($Transcript -match '(?m)^#{1,3}\s*(Test Strategy|Testing Approach|Test Plan)\s*$')
    $hasTestResults = ($Transcript -match '(?m)^#{1,3}\s*(Test Results|Validation Results|Test Execution)\s*$')
    $hasCoverage = ($Transcript -match '(?m)^#{1,3}\s*(Coverage|Test Coverage|Acceptance Criteria)\s*$')

    if (-not $hasTestStrategy) {
        $missing += 'Test Strategy/Testing Approach/Test Plan (as section header)'
    }
    if (-not $hasTestResults) {
        $missing += 'Test Results/Validation Results/Test Execution (as section header)'
    }
    if (-not $hasCoverage) {
        $missing += 'Coverage/Test Coverage/Acceptance Criteria (as section header)'
    }

    return $missing
}

try {
    if (-not [Console]::IsInputRedirected) {
        exit 0
    }

    $inputJson = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($inputJson)) {
        exit 0
    }

    $hookInput = $inputJson | ConvertFrom-Json -ErrorAction Stop

    if (-not (Test-IsQAAgent -HookInput $hookInput)) {
        exit 0
    }

    $transcriptPath = Get-TranscriptPath -HookInput $hookInput
    if ($null -eq $transcriptPath) {
        # Issue #15: Log why transcript path is null for troubleshooting
        if (-not ($hookInput.PSObject.Properties['transcript_path'])) {
            Write-Warning "QA validator: No transcript_path property in hook input. Agent may not have provided transcript. Validation skipped."
        }
        elseif ([string]::IsNullOrWhiteSpace($hookInput.transcript_path)) {
            Write-Warning "QA validator: transcript_path property exists but is empty/whitespace. Validation skipped."
        }
        else {
            Write-Warning "QA validator: Transcript file does not exist at '$($hookInput.transcript_path)'. Agent may have failed or transcript not written. Validation skipped."
        }
        exit 0
    }

    $transcript = Get-Content $transcriptPath -Raw -ErrorAction Stop
    $missingSections = Get-MissingQASections -Transcript $transcript

    if ($missingSections.Count -gt 0) {
        $missingList = $missingSections -join ', '
        Write-Output "`n**QA VALIDATION FAILURE**: QA agent report is incomplete and does NOT meet SESSION-PROTOCOL requirements.`n`nMissing required sections: $missingList`n`nACTION REQUIRED: Re-run QA agent with complete report including all required sections per .agents/SESSION-PROTOCOL.md`n"
        Write-Warning "QA validation failed: Missing sections - $missingList"
    }
    else {
        Write-Output "`n**QA Validation PASSED**: All required sections present in QA report.`n"
    }

    # Issue #13: Add JSON output for machine-readable validation results
    $validationResult = @{
        validation_passed = ($missingSections.Count -eq 0)
        missing_sections = $missingSections
        transcript_path = $transcriptPath
    }
    Write-Output ($validationResult | ConvertTo-Json -Compress)

    exit 0
}
catch [System.IO.IOException], [System.UnauthorizedAccessException] {
    Write-Error "QA validator file error: Cannot read transcript at $transcriptPath - $($_.Exception.Message)"
    Write-Output "`n**QA Validation ERROR**: Cannot access QA agent transcript file. Validation skipped.`n"
    exit 0
}
catch {
    Write-Error "QA validator unexpected error: $($_.Exception.GetType().FullName) - $($_.Exception.Message)"
    Write-Output "`n**QA Validation ERROR**: Unexpected error during validation. MUST investigate: $($_.Exception.Message)`n"
    exit 0
}
