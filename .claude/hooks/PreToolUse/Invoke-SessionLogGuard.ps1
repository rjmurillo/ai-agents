<#
.SYNOPSIS
    Blocks git commit without session log evidence.

.DESCRIPTION
    Claude Code PreToolUse hook that enforces session logging before commits.
    Prevents untracked work by requiring a session log for the current date.

    Checks:
    1. Command is git commit
    2. Session log exists for today in .agents/sessions/
    3. Session log contains work evidence (non-empty)

    Part of Tier 2 enforcement hooks (Issue #773, Session tracking).

.NOTES
    Hook Type: PreToolUse
    Exit Codes:
        0 = Allow (not commit, or log exists)
        2 = Block (commit without session log)

    EXIT CODE SEMANTICS (Claude Hook Convention):
    Exit code 2 signals BLOCKING. Claude interprets this as "stop processing
    and show user the reason."

.LINK
    .agents/SESSION-PROTOCOL.md
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-ProjectDirectory {
    if (-not [string]::IsNullOrWhiteSpace($env:CLAUDE_PROJECT_DIR)) {
        return $env:CLAUDE_PROJECT_DIR
    }
    return Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
}

function Test-GitCommitCommand {
    param([string]$Command)

    if ([string]::IsNullOrWhiteSpace($Command)) {
        return $false
    }

    return $Command -match '(?:^|\s)git\s+(commit|ci)'
}

function Get-TodaySessionLog {
    param([string]$SessionsDir)

    if (-not (Test-Path $SessionsDir)) {
        return $null
    }

    $today = Get-Date -Format "yyyy-MM-dd"
    $logs = @(Get-ChildItem -Path $SessionsDir -Filter "$today-session-*.json" -File -ErrorAction SilentlyContinue)

    if ($logs.Count -eq 0) {
        return $null
    }

    # Return most recent log
    return $logs | Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

function Test-SessionLogEvidence {
    param([string]$SessionLogPath)

    try {
        $content = Get-Content $SessionLogPath -Raw -ErrorAction Stop

        # Must have substantial content (not just placeholder)
        if ($content.Length -lt 100) {
            return @{
                Valid = $false
                Reason = "Session log exists but is empty"
            }
        }

        # Optionally validate JSON structure
        try {
            $json = $content | ConvertFrom-Json
            if ($json.PSObject.Properties.Count -lt 2) {
                return @{
                    Valid = $false
                    Reason = "Session log lacks required sections"
                }
            }
        }
        catch {
            # Not JSON is acceptable (could be markdown log)
        }

        return @{
            Valid = $true
            Content = $content.Substring(0, 200)
        }
    }
    catch {
        return @{
            Valid = $false
            Reason = "Error reading session log: $($_.Exception.Message)"
        }
    }
}

# Main execution
try {
    # Read JSON input from stdin
    if (-not [Console]::IsInputRedirected) {
        exit 0
    }

    $inputJson = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($inputJson)) {
        exit 0
    }

    $hookInput = $inputJson | ConvertFrom-Json -ErrorAction Stop

    # Extract command from tool_input
    if (-not $hookInput.tool_input -or -not $hookInput.tool_input.command) {
        exit 0
    }

    $command = $hookInput.tool_input.command

    # Test if this is a git commit command
    if (-not (Test-GitCommitCommand -Command $command)) {
        exit 0
    }

    # Check for session log
    $projectDir = Get-ProjectDirectory
    $sessionsDir = Join-Path $projectDir ".agents" "sessions"
    $sessionLog = Get-TodaySessionLog -SessionsDir $sessionsDir

    if ($null -eq $sessionLog) {
        $output = @"

## ⛔ BLOCKED: No Session Log Found

**YOU MUST create a session log before committing.**

### Why Session Logs Matter
- Evidence of work performed
- Compliance tracking (ADR-007, ADR-033)
- Context for future sessions
- Audit trail for peer review

### How to Create a Session Log

**Option 1: Use /session-init skill**
``````
/session-init
``````

**Option 2: Create manually**
``````powershell
pwsh scripts/sessions/Initialize-SessionLog.ps1
``````

Session logs go in: ``.agents/sessions/$(Get-Date -Format 'yyyy-MM-dd')-session-NN.json``

**Current Date**: $(Get-Date -Format 'yyyy-MM-dd')
**Sessions Directory**: $sessionsDir

See: ``.agents/SESSION-PROTOCOL.md`` for full details.

"@
        Write-Output $output
        Write-Error "Session blocked: No session log found for today"
        exit 2
    }

    # Validate session log has content
    $evidence = Test-SessionLogEvidence -SessionLogPath $sessionLog.FullName

    if (-not $evidence.Valid) {
        $output = @"

## ⛔ BLOCKED: Session Log Empty or Invalid

**Reason**: $($evidence.Reason)

### Fix

Edit the session log and add substantial work evidence:

``````
$($sessionLog.FullName)
``````

Session log MUST contain:
- Timestamp of work
- Description of tasks performed
- Tool usage evidence
- Key decisions made

**Current Session Log**: $($sessionLog.Name)

"@
        Write-Output $output
        Write-Error "Session blocked: Session log has insufficient evidence"
        exit 2
    }

    # Session log valid - allow commit
    exit 0
}
catch {
    # Fail-open on errors (don't block on infrastructure issues)
    Write-Warning "Session log guard error: $($_.Exception.Message)"
    exit 0
}
