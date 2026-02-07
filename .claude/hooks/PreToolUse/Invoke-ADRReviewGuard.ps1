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

# Import shared hook utilities
Import-Module "$PSScriptRoot/../Common/HookUtilities.psm1" -Force

function Get-StagedADRChanges {
    try {
        $stagedFiles = & git diff --cached --name-only 2>&1
        if ($LASTEXITCODE -ne 0) {
            # Fail-closed: git errors should block commits to prevent bypass
            throw "git diff --cached failed with exit code $LASTEXITCODE : $stagedFiles"
        }

        if (-not $stagedFiles) {
            return @()
        }

        # Filter for ADR files (case-insensitive for cross-platform support)
        $adrFiles = @($stagedFiles | Where-Object { $_ -imatch 'ADR-\d+\.md$' })
        return $adrFiles
    }
    catch {
        # Re-throw to fail-closed
        throw "Failed to check staged ADR changes: $($_.Exception.Message)"
    }
}

function Test-ADRReviewEvidence {
    param(
        [string]$SessionLogPath,
        [string]$ProjectDir
    )

    try {
        $content = Get-Content $SessionLogPath -Raw -ErrorAction Stop

        # Check for adr-review execution evidence
        # Per rjmurillo #2679845429: Requires both session log mention AND debate log artifact
        $patterns = @(
            '/adr-review',                              # Skill invocation
            'adr-review skill',                         # Explicit skill reference
            'ADR Review Protocol',                      # Skill output header
            '(?s)multi-agent consensus.{0,200}\bADR\b', # Consensus specific to ADR, with proximity
            '(?s)\barchitect\b.{0,80}\bplanner\b.{0,80}\bqa\b'    # Agent workflow pattern with proximity
        )

        $foundPattern = $false
        $matchedPattern = ""

        foreach ($pattern in $patterns) {
            if ($content -match $pattern) {
                $foundPattern = $true
                $matchedPattern = $pattern
                break
            }
        }

        if (-not $foundPattern) {
            return @{
                Complete = $false
                Reason = "No adr-review evidence in session log"
            }
        }

        # Verify debate log artifact exists (rjmurillo #2679844056, #2679845429)
        # The adr-review skill creates debate logs in .agents/analysis/
        $analysisDir = Join-Path $ProjectDir ".agents" "analysis"
        if (Test-Path $analysisDir) {
            $debateLogs = @(Get-ChildItem -Path $analysisDir -Filter "*debate*.md" -File -ErrorAction SilentlyContinue)
            if ($debateLogs.Count -eq 0) {
                return @{
                    Complete = $false
                    Reason = "Session log mentions adr-review, but no debate log artifact found in .agents/analysis/"
                }
            }
        }
        else {
            return @{
                Complete = $false
                Reason = "Session log mentions adr-review, but .agents/analysis/ directory does not exist"
            }
        }

        return @{
            Complete = $true
            Evidence = "ADR review evidence found: matched pattern '$matchedPattern' and debate log artifact exists"
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
            Reason = "Session log contains invalid data. Check file format or recreate."
        }
    }
    catch {
        return @{
            Complete = $false
            Reason = "Error reading session log: $($_.Exception.GetType().Name) - $($_.Exception.Message)"
        }
    }
}

# Main execution
try {
    # Compute date once to avoid midnight race condition (Copilot #2679880612)
    $today = Get-Date -Format 'yyyy-MM-dd'

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
    # Wrap in dedicated try/catch: Get-StagedADRChanges throws on git errors for fail-closed.
    # The outer catch exits 0 (fail-open for infrastructure), so we must catch git errors here
    # and exit 2 to preserve the fail-closed security posture.
    try {
        $adrChanges = @(Get-StagedADRChanges)
    }
    catch {
        $errorMsg = "Staged ADR check failed (fail-closed): $($_.Exception.Message)"
        Write-Warning $errorMsg
        [Console]::Error.WriteLine($errorMsg)
        try {
            $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
            $hookDir = Split-Path -Parent $scriptDir
            $auditLogPath = Join-Path $hookDir "audit.log"
            $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            Add-Content -Path $auditLogPath -Value "[$timestamp] [ADRReviewGuard] $errorMsg" -ErrorAction SilentlyContinue
        }
        catch {
            # Silent fallback if audit log write fails
        }
        exit 2
    }
    if ($adrChanges.Count -eq 0) {
        # No ADR changes, allow commit
        exit 0
    }

    # ADR changes detected - verify review was done
    $projectDir = Get-ProjectDirectory
    $sessionsDir = Join-Path $projectDir ".agents" "sessions"
    $sessionLog = Get-TodaySessionLog -SessionsDir $sessionsDir -Date $today

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
    $evidence = Test-ADRReviewEvidence -SessionLogPath $sessionLog.FullName -ProjectDir $projectDir

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
    $errorMsg = "ADR review guard error: $($_.Exception.GetType().Name) - $($_.Exception.Message)"
    Write-Warning $errorMsg
    [Console]::Error.WriteLine($errorMsg)

    # Audit log entry for infrastructure errors
    try {
        $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
        $hookDir = Split-Path -Parent $scriptDir
        $auditLogPath = Join-Path $hookDir "audit.log"
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $logEntry = "[$timestamp] [ADRReviewGuard] $errorMsg"
        Add-Content -Path $auditLogPath -Value $logEntry -ErrorAction SilentlyContinue
    }
    catch {
        # Silent fallback if audit log write fails
    }

    exit 0
}
