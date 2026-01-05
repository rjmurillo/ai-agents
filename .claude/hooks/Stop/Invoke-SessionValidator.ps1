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
        0 = Success, validation result in stdout JSON
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

    # Get project directory
    $projectDir = $env:CLAUDE_PROJECT_DIR
    if ([string]::IsNullOrWhiteSpace($projectDir)) {
        $projectDir = $hookInput.cwd
    }

    # Check for session log
    $sessionsDir = Join-Path $projectDir ".agents" "sessions"
    if (-not (Test-Path $sessionsDir)) {
        # No sessions directory, allow stop (might be investigation session)
        exit 0
    }

    # Find today's session logs
    $today = Get-Date -Format "yyyy-MM-dd"
    $todaySessionLogs = Get-ChildItem -Path $sessionsDir -Filter "$today-session-*.md" -File -ErrorAction SilentlyContinue

    if ($todaySessionLogs.Count -eq 0) {
        # No session log for today - force continuation
        $response = @{
            continue = $true
            reason = "Session log missing. MUST create session log at .agents/sessions/$today-session-NN.md per SESSION-PROTOCOL.md"
        } | ConvertTo-Json -Compress

        Write-Output $response
        exit 0
    }

    # Get the most recent session log
    $latestLog = $todaySessionLogs | Sort-Object LastWriteTime -Descending | Select-Object -First 1

    # Read session log content
    $logContent = Get-Content $latestLog.FullName -Raw -ErrorAction Stop

    # Check for required sections
    $requiredSections = @(
        '## Session Context',
        '## Work Log',
        '## Decisions',
        '## Outcomes',
        '## Files Changed'
    )

    $missingSections = @()
    foreach ($section in $requiredSections) {
        if ($logContent -notmatch [regex]::Escape($section)) {
            $missingSections += $section
        }
    }

    # Check if Outcomes section is filled (not just header)
    if ($logContent -match '## Outcomes\s*\n\s*\(To be filled') {
        $missingSections += '## Outcomes (content required, not just placeholder)'
    }

    if ($missingSections.Count -gt 0) {
        # Session log incomplete - force continuation
        $missingList = $missingSections -join ', '
        $response = @{
            continue = $true
            reason = "Session log incomplete in $($latestLog.Name). Missing or incomplete sections: $missingList. MUST complete per SESSION-PROTOCOL.md"
        } | ConvertTo-Json -Compress

        Write-Output $response
        exit 0
    }

    # Session log is complete, allow stop
    exit 0
}
catch {
    # On error, allow stop (fail open)
    Write-Warning "Session validation failed: $($_.Exception.Message)"
    exit 0
}
