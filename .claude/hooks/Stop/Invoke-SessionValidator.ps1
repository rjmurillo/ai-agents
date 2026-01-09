<#
.SYNOPSIS
    Validates session log completeness before Claude stops responding.

.DESCRIPTION
    Claude Code Stop hook that verifies the session log exists and contains
    required sections. If incomplete, forces Claude to continue working until
    the session log is properly completed per SESSION-PROTOCOL requirements.

    Part of the hooks expansion implementation (Issue #773, Phase 2).

.NOTES
    Hook Type: Stop
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

function Write-ContinueResponse {
    param([string]$Reason)

    $response = @{
        continue = $true
        reason = $Reason
    } | ConvertTo-Json -Compress

    Write-Output $response
    exit 0
}

function Get-ProjectDirectory {
    param($HookInput)

    if (-not [string]::IsNullOrWhiteSpace($env:CLAUDE_PROJECT_DIR)) {
        return $env:CLAUDE_PROJECT_DIR
    }
    return $HookInput.cwd
}

function Get-TodaySessionLogs {
    param([string]$SessionsDir)

    # Return different sentinel values to distinguish cases
    if (-not (Test-Path $SessionsDir)) {
        # Directory doesn't exist - not an error (project may not use sessions)
        return @{ DirectoryMissing = $true }
    }

    $today = Get-Date -Format "yyyy-MM-dd"
    $logs = Get-ChildItem -Path $SessionsDir -Filter "$today-session-*.md" -File -ErrorAction SilentlyContinue

    if ($logs.Count -eq 0) {
        # Directory exists but no log for today - protocol violation
        return @{ LogMissing = $true; Today = $today }
    }

    # Return the most recent log file
    return $logs | Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

function Get-MissingSections {
    param([string]$LogContent)

    $requiredSections = @(
        '## Session Context',
        '## Implementation Plan',
        '## Work Log',
        '## Decisions',
        '## Outcomes',
        '## Files Changed',
        '## Follow-up Actions'
    )

    $missing = @()
    foreach ($section in $requiredSections) {
        if ($LogContent -notmatch [regex]::Escape($section)) {
            $missing += $section
        }
    }

    # Robust placeholder detection: Check if ## Outcomes section exists but is suspiciously short
    # or contains common placeholder patterns (TBD, TODO, To be filled, Coming soon, etc.)
    if ($LogContent -match '## Outcomes([^\#]*?)(?=\n##|\z)') {
        $outcomesSection = $Matches[1]
        $placeholderPatterns = @('to be filled', 'TBD', 'TODO', 'coming soon', '\(pending\)', '\[pending\]')

        $hasPlaceholder = $false
        foreach ($pattern in $placeholderPatterns) {
            if ($outcomesSection -match $pattern) {
                $hasPlaceholder = $true
                break
            }
        }

        # Also check if section is suspiciously short (less than 50 chars excluding heading)
        $isTooShort = $outcomesSection.Trim().Length -lt 50

        if ($hasPlaceholder -or $isTooShort) {
            $missing += '## Outcomes (section incomplete or contains placeholder text)'
        }
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
    $projectDir = Get-ProjectDirectory -HookInput $hookInput
    $sessionsDir = Join-Path $projectDir ".agents" "sessions"

    $result = Get-TodaySessionLogs -SessionsDir $sessionsDir

    # Handle different return cases
    if ($result -is [hashtable]) {
        if ($result.DirectoryMissing) {
            # Directory doesn't exist - project may not use sessions, exit silently
            exit 0
        }
        if ($result.LogMissing) {
            # Directory exists but no log - protocol violation
            Write-ContinueResponse "Session log missing. MUST create session log at .agents/sessions/$($result.Today)-session-NN.md per SESSION-PROTOCOL.md"
        }
    }

    # At this point, $result should be a FileInfo object
    $logContent = Get-Content $result.FullName -Raw -ErrorAction Stop
    $missingSections = Get-MissingSections -LogContent $logContent

    if ($missingSections.Count -gt 0) {
        $missingList = $missingSections -join ', '
        Write-ContinueResponse "Session log incomplete in $($result.Name). Missing or incomplete sections: $missingList. MUST complete per SESSION-PROTOCOL.md"
    }

    exit 0
}
catch [System.IO.IOException], [System.UnauthorizedAccessException] {
    Write-Error "Session validator file error: $($_.Exception.Message)"
    Write-ContinueResponse "Session validation failed: Cannot read session log. MUST investigate file system issue. Error: $($_.Exception.Message)"
}
catch {
    Write-Error "Session validator unexpected error: $($_.Exception.GetType().FullName) - $($_.Exception.Message)"
    Write-ContinueResponse "Session validation encountered unexpected error. MUST investigate: $($_.Exception.GetType().FullName) - $($_.Exception.Message)"
}
