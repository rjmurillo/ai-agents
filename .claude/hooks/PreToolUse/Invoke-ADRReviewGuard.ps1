<#
.SYNOPSIS
    Blocks git commit with ADR changes unless adr-review skill was executed.

.DESCRIPTION
    Claude Code PreToolUse hook that enforces ADR review before commit.
    Detects ADR file modifications and blocks commit unless the adr-review
    skill ran in the current session.

    Checks:
    1. Command is git commit
    2. Changes include ADR files (ADR-*.md)
    3. Session log contains adr-review evidence
    4. adr-review output shows multi-agent consensus

    Part of Tier 2 enforcement hooks (Issue #773, ADR review enforcement).

.NOTES
    Hook Type: PreToolUse
    Exit Codes:
        0 = Allow (not commit, or no ADR changes, or review done)
        2 = Block (ADR changes without review)

    EXIT CODE SEMANTICS (Claude Hook Convention):
    Exit code 2 signals BLOCKING. Claude interprets this as "stop processing
    and show user the reason."

.LINK
    .claude/skills/adr-review/SKILL.md
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

function Get-StagedADRChanges {
    try {
        $stagedFiles = & git diff --cached --name-only 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $stagedFiles) {
            return @()
        }

        # Filter for ADR files (case-insensitive for cross-platform support)
        $adrFiles = @($stagedFiles | Where-Object { $_ -imatch 'ADR-\d+\.md$' })
        return $adrFiles
    }
    catch {
        return @()
    }
}

function Test-ADRReviewEvidence {
    param([string]$SessionLogPath)

    try {
        $content = Get-Content $SessionLogPath -Raw -ErrorAction Stop

        # Check for adr-review execution evidence
        if ($content -match 'adr-review|ADR.*review|multi-agent.*consensus') {
            return @{
                Complete = $true
                Evidence = "ADR review evidence found in session log"
            }
        }

        return @{
            Complete = $false
            Reason = "No adr-review evidence in session log"
        }
    }
    catch {
        return @{
            Complete = $false
            Reason = "Error reading session log: $($_.Exception.Message)"
        }
    }
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

    return $logs | Sort-Object LastWriteTime -Descending | Select-Object -First 1
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

    # Check for ADR file changes
    $adrChanges = @(Get-StagedADRChanges)
    if ($adrChanges.Count -eq 0) {
        # No ADR changes, allow commit
        exit 0
    }

    # ADR changes detected - verify review was done
    $projectDir = Get-ProjectDirectory
    $sessionsDir = Join-Path $projectDir ".agents" "sessions"
    $sessionLog = Get-TodaySessionLog -SessionsDir $sessionsDir

    if ($null -eq $sessionLog) {
        $output = @"

## ⛔ BLOCKED: ADR Changes Without Review

**YOU MUST run /adr-review before committing ADR changes.**

### Changes Detected

$($adrChanges -join "`n")

### Required Action

Invoke the adr-review skill for multi-agent consensus:

``````
/adr-review [ADR-path]
``````

This ensures 6-agent debate (architect, critic, independent-thinker, security, analyst, high-level-advisor) before ADR acceptance.

**Why**: ADR changes impact system architecture. Multi-agent review prevents oversights and catches edge cases.

**Skill**: ``.claude/skills/adr-review/SKILL.md``

"@
        Write-Output $output
        # Use Console.Error to avoid exception from Write-Error with Stop action preference
        [Console]::Error.WriteLine("Session blocked: ADR changes without review")
        exit 2
    }

    # Check for review evidence in session log
    $evidence = Test-ADRReviewEvidence -SessionLogPath $sessionLog.FullName

    if (-not $evidence.Complete) {
        $output = @"

## ⛔ BLOCKED: ADR Changes Without Review

**YOU MUST run /adr-review before committing ADR changes.**

### Changes Detected

$($adrChanges -join "`n")

### Problem

$($evidence.Reason). Session log needs evidence of /adr-review execution.

### Required Action

Invoke the adr-review skill for multi-agent consensus:

``````
/adr-review [ADR-path]
``````

This ensures 6-agent debate (architect, critic, independent-thinker, security, analyst, high-level-advisor) before ADR acceptance.

**Skill**: ``.claude/skills/adr-review/SKILL.md``
**Session Log**: $($sessionLog.Name)

"@
        Write-Output $output
        # Use Console.Error to avoid exception from Write-Error with Stop action preference
        [Console]::Error.WriteLine("Session blocked: ADR review not completed in session")
        exit 2
    }

    # Review evidence found - allow commit
    exit 0
}
catch {
    # Fail-open on errors (don't block on infrastructure issues)
    Write-Warning "ADR review guard error: $($_.Exception.Message)"
    exit 0
}
