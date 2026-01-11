<#
.SYNOPSIS
    Enforces ADR-007 memory-first protocol with hybrid education/blocking strategy.

.DESCRIPTION
    Claude Code SessionStart hook that verifies memory retrieval evidence before
    allowing work to proceed. Uses hybrid enforcement:

    - First 3 invocations: Educational guidance (exit 0, inject context)
    - After threshold: BLOCKING gate (exit 2) if evidence missing

    Evidence verification checks session log protocolCompliance.sessionStart for:
    1. serenaActivated.Complete = true
    2. handoffRead.Complete = true
    3. memoriesLoaded.Evidence contains memory names

    Part of Tier 2 enforcement hooks (Issue #773, Protocol enforcement).

.NOTES
    Hook Type: SessionStart
    Exit Codes:
        0 = Success (guidance injected or evidence complete)
        2 = Block session (evidence missing after education threshold)

    EXIT CODE SEMANTICS (Claude Hook Convention):
    Exit code 2 signals BLOCKING. Claude interprets this as "stop processing
    and show user the reason."

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
    catch {
        return @{
            Complete = $false
            Reason = "Error parsing session log: $($_.Exception.Message)"
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

    # If no session log exists, provide guidance (non-blocking)
    if ($todayLogs.Count -eq 0) {
        $output = @"

## ADR-007 Memory-First Protocol

**No session log found for today.** Create one early in session:
- Use ``/session-init`` skill, OR
- Create ``.agents/sessions/$today-session-NN.json``

**Required evidence in session log**:
- ``protocolCompliance.sessionStart.serenaActivated.Complete = true``
- ``protocolCompliance.sessionStart.handoffRead.Complete = true``
- ``protocolCompliance.sessionStart.memoriesLoaded.Evidence`` contains memory names

See: ``.agents/SESSION-PROTOCOL.md`` Phase 1-2

"@
        Write-Output $output
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

    if ($count -le $EDUCATION_THRESHOLD) {
        # Education phase
        $output = @"

## ⚠️  ADR-007 Memory-First: Evidence Missing (Warning $count/$EDUCATION_THRESHOLD)

**Reason**: $($evidence.Reason)

Complete these steps NOW to build evidence:

1. **Initialize Serena** (REQUIRED):
   ``````
   mcp__serena__activate_project
   mcp__serena__initial_instructions
   ``````

2. **Load Project Context** (REQUIRED):
   - Read ``.agents/HANDOFF.md``
   - Read ``memory-index`` from Serena
   - Read task-relevant memories listed in memory-index

3. **Document Evidence** (REQUIRED):
   - Session log MUST show tool outputs from steps 1-2
   - ``protocolCompliance.sessionStart.memoriesLoaded`` MUST list specific memories

**Why This Matters**: Without memory retrieval, you will repeat past mistakes, violate learned constraints, and ignore architectural decisions.

**After $EDUCATION_THRESHOLD warnings, this becomes BLOCKING.**

"@
        Write-Output $output
        exit 0
    }
    else {
        # Blocking phase
        $output = @"

## ⛔ BLOCKING: Memory-First Protocol Violation (ADR-007)

**YOU MUST retrieve context BEFORE reasoning. This is non-negotiable.**

### Missing Required Evidence

**Reason**: $($evidence.Reason)

Complete these steps NOW (in order):

1. **Initialize Serena** (REQUIRED):
   ``````
   mcp__serena__activate_project
   mcp__serena__initial_instructions
   ``````

2. **Load Project Context** (REQUIRED):
   - Read ``.agents/HANDOFF.md``
   - Read ``memory-index`` from Serena
   - Read task-relevant memories listed in memory-index

3. **Document Evidence** (REQUIRED):
   - Session log MUST show tool outputs from steps 1-2
   - ``protocolCompliance.sessionStart.memoriesLoaded`` MUST list specific memories

**Why This Matters**: Without memory retrieval, you will repeat past mistakes, violate learned constraints, and ignore architectural decisions. Verification-based enforcement achieves 100% compliance vs <50% with guidance alone.

**Cannot proceed until complete.** See: ``.agents/SESSION-PROTOCOL.md`` Phase 1-2

"@
        Write-Output $output
        # Use Console.Error to avoid exception from Write-Error with Stop action preference
        [Console]::Error.WriteLine("Session blocked: ADR-007 memory-first evidence missing after $count invocations")
        exit 2
    }
}
catch {
    # Fail-open on errors (don't block session startup)
    Write-Warning "Memory-first enforcer error: $($_.Exception.Message)"
    exit 0
}
