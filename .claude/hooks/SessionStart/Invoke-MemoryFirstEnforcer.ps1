<#
.SYNOPSIS
    Enforces ADR-007 memory-first protocol with hybrid education/escalation strategy.

.DESCRIPTION
    Claude Code SessionStart hook that verifies memory retrieval evidence before
    allowing work to proceed. Uses hybrid enforcement:

    - First 3 invocations: Educational guidance (inject context)
    - After threshold: Strong warning with escalated urgency (inject context)

    Evidence verification checks session log protocolCompliance.sessionStart for:
    1. serenaActivated.Complete = true
    2. handoffRead.Complete = true
    3. memoriesLoaded.Evidence contains memory names

    Part of Tier 2 enforcement hooks (Issue #773, Protocol enforcement).

    NOTE: SessionStart hooks cannot block (exit 2 only shows stderr as error,
    does not block the session, and prevents stdout from being injected).
    All enforcement is via context injection (exit 0 with stdout).

.NOTES
    Hook Type: SessionStart
    Exit Codes:
        0 = Success (guidance or warning injected into Claude's context)

.LINK
    .agents/SESSION-PROTOCOL.md
    .agents/architecture/ADR-007-memory-first-architecture.md
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Import shared hook utilities
Import-Module "$PSScriptRoot/../Common/HookUtilities.psm1" -Force

# Constants
$EDUCATION_THRESHOLD = 3

function Test-MemoryEvidence {
    param([string]$SessionLogPath)

    try {
        $content = Get-Content $SessionLogPath -Raw | ConvertFrom-Json

        # Check protocolCompliance.sessionStart section
        if (-not $content.protocolCompliance -or -not $content.protocolCompliance.sessionStart) {
            return @{
                Complete = $false
                Reason = "Missing protocolCompliance.sessionStart section"
            }
        }

        $sessionStart = $content.protocolCompliance.sessionStart

        # Check Serena activation (fixes Copilot #2678729134 - lowercase 'complete')
        if (-not $sessionStart.serenaActivated -or -not $sessionStart.serenaActivated.complete) {
            return @{
                Complete = $false
                Reason = "Serena not initialized"
            }
        }

        # Check HANDOFF.md read (fixes Copilot #2678729134 - lowercase 'complete')
        if (-not $sessionStart.handoffRead -or -not $sessionStart.handoffRead.complete) {
            return @{
                Complete = $false
                Reason = "HANDOFF.md not read"
            }
        }

        # Check memories loaded with evidence (fixes Copilot #2678729134 - lowercase 'complete')
        if (-not $sessionStart.memoriesLoaded -or -not $sessionStart.memoriesLoaded.complete) {
            return @{
                Complete = $false
                Reason = "Memories not loaded"
            }
        }

        $evidence = $sessionStart.memoriesLoaded.Evidence
        if ([string]::IsNullOrWhiteSpace($evidence)) {
            return @{
                Complete = $false
                Reason = "Memory evidence is empty"
            }
        }

        # Evidence complete
        return @{
            Complete = $true
            Evidence = $evidence
        }
    }
    catch [System.UnauthorizedAccessException] {
        return @{
            Complete = $false
            Reason = "Session log is locked or you lack permissions. Close editors and retry."
        }
    }
    catch [System.IO.FileNotFoundException] {
        return @{
            Complete = $false
            Reason = "Session log was deleted after detection. Create a new session log."
        }
    }
    catch [System.ArgumentException] {
        return @{
            Complete = $false
            Reason = "Session log contains invalid JSON. Check file format or recreate."
        }
    }
    catch {
        return @{
            Complete = $false
            Reason = "Error parsing session log: $($_.Exception.GetType().Name) - $($_.Exception.Message)"
        }
    }
}

function Get-InvocationCount {
    param(
        [string]$StateDir,
        [string]$Today
    )

    $stateFile = Join-Path $StateDir "memory-first-counter.txt"
    if (-not (Test-Path $stateFile)) {
        return 0
    }

    try {
        $content = Get-Content $stateFile -Raw
        $lines = $content.Trim() -split '\r?\n'

        # Format: count|date (e.g., "3|2026-01-10")
        if ($lines.Count -eq 2) {
            $storedCount = [int]$lines[0]
            $storedDate = $lines[1]

            # Reset counter if date changed (cursor #2678568713, Copilot #2678558279)
            if ($storedDate -ne $Today) {
                return 0
            }

            return $storedCount
        }

        # Legacy format (just a number) - assume same day
        return [int]$content.Trim()
    }
    catch {
        return 0
    }
}

function Increment-InvocationCount {
    param(
        [string]$StateDir,
        [string]$Today
    )

    if (-not (Test-Path $StateDir)) {
        New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
    }

    $stateFile = Join-Path $StateDir "memory-first-counter.txt"
    $count = (Get-InvocationCount -StateDir $StateDir -Today $Today) + 1

    # Store count and date (cursor #2678568713, Copilot #2678558279)
    Set-Content -Path $stateFile -Value "$count`n$Today"
    return $count
}

# Main execution
try {
    # Compute date once to avoid midnight race condition (Copilot #2678558267)
    $today = Get-Date -Format 'yyyy-MM-dd'

    $projectDir = Get-ProjectDirectory
    $sessionsDir = Join-Path $projectDir ".agents" "sessions"
    $stateDir = Join-Path $projectDir ".agents" ".hook-state"

    # Get today's session logs
    $todayLogs = @(Get-TodaySessionLogs -SessionsDir $sessionsDir)

    # If no session log exists, provide compact guidance (non-blocking)
    if ($todayLogs.Count -eq 0) {
        Write-Output "`nADR-007: No session log for today. Run ``/session-init``. Protocol details in AGENTS.md.`n"
        exit 0
    }

    # Check most recent session log for evidence
    $latestLog = $todayLogs | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $evidence = Test-MemoryEvidence -SessionLogPath $latestLog.FullName

    # If evidence complete, allow
    if ($evidence.Complete) {
        Write-Output "`n✅ ADR-007 Memory-First: Evidence verified in session log.`n"
        exit 0
    }

    # Evidence missing - check invocation count for education vs blocking
    $count = Increment-InvocationCount -StateDir $stateDir -Today $today

    $severity = if ($count -le $EDUCATION_THRESHOLD) { "Warning $count/$EDUCATION_THRESHOLD" } else { "VIOLATION (warning $count)" }
    Write-Output "`nADR-007 $severity : $($evidence.Reason). Complete: Serena init, HANDOFF.md read, memory retrieval. See AGENTS.md Session Protocol Gates.`n"
    exit 0
}
catch {
    # Fail-open on errors (don't block session startup)
    Write-Warning "Memory-first enforcer error: $($_.Exception.Message)"
    exit 0
}
