<#
.SYNOPSIS
    Enforces session protocol initialization at session start.

.DESCRIPTION
    Claude Code SessionStart hook that warns against working on main/master
    branches and injects git state into Claude's context.

    Checks:
    1. Current branch is not main/master (WARNING injected into context)
    2. Git status and recent commits (injected into context)
    3. Session log status for today (reported, not blocking)

    Part of Tier 1 enforcement hooks (Session initialization).

    NOTE: SessionStart hooks cannot block (exit 2 only shows stderr as error,
    does not block the session, and prevents stdout from being injected).
    Branch protection at commit time is enforced by PreToolUse hooks.

.NOTES
    Hook Type: SessionStart
    Exit Codes:
        0 = Success (stdout injected into Claude's context)

.LINK
    .agents/SESSION-PROTOCOL.md
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Import shared hook utilities
Import-Module "$PSScriptRoot/../Common/HookUtilities.psm1" -Force

function Get-CurrentBranch {
    try {
        $branch = & git rev-parse --abbrev-ref HEAD 2>$null
        if ($LASTEXITCODE -eq 0) {
            return $branch.Trim()
        }
        return $null
    }
    catch {
        return $null
    }
}

function Test-IsMainOrMasterBranch {
    param([string]$Branch)

    # Check if branch is main or master (common default branches)
    if ([string]::IsNullOrWhiteSpace($Branch)) {
        return $false
    }

    $protectedBranches = @('main', 'master')
    return $protectedBranches -contains $Branch
}

function Get-GitStatus {
    try {
        $status = & git status --short 2>$null
        if ($LASTEXITCODE -eq 0) {
            return $status
        }
        return "(unable to get git status)"
    }
    catch {
        return "(error getting git status)"
    }
}

function Get-RecentCommits {
    param([int]$Count = 3)

    try {
        $commits = & git log --oneline -n $Count 2>$null
        if ($LASTEXITCODE -eq 0) {
            return $commits
        }
        return "(unable to get recent commits)"
    }
    catch {
        return "(error getting commits)"
    }
}

# Main execution
try {
    $projectDir = Get-ProjectDirectory
    $currentBranch = Get-CurrentBranch

    # WARNING: Check if on protected branch
    # NOTE: SessionStart hooks cannot block (exit 2 only shows stderr, prevents
    # stdout injection). Commit-time protection is enforced by PreToolUse hooks.
    if (Test-IsMainOrMasterBranch -Branch $currentBranch) {
        $output = @"

## WARNING: On Protected Branch

**Switch to a feature branch before making changes.**

**Current Branch**: ``$currentBranch``

Direct commits to main/master are blocked by pre-commit hooks.
Create or switch to a feature branch:

``````bash
git checkout -b feat/your-feature-name
``````

### REMINDER: Skill-First Pattern + Retrieval-Led Reasoning

**Before using raw git/gh commands, check if a skill exists:**
- Git operations: Check ``.claude/skills/git-*/``
- GitHub operations: Check ``.claude/skills/github/`` (mandatory per usage-mandatory memory)
- Prefer retrieval-led reasoning: Read skill documentation, don't rely on pre-training

**Process:**
1. Identify operation type (PR creation, merge, etc.)
2. Check SKILL-QUICK-REF.md for corresponding skill
3. Read skill's SKILL.md for current, tested patterns
4. Use skill instead of raw commands

"@
        Write-Output $output
        exit 0
    }

    # NON-BLOCKING: Inject git state into context
    $gitStatus = Get-GitStatus
    $recentCommits = Get-RecentCommits

    # Check for session log
    $sessionsDir = Join-Path $projectDir ".agents" "sessions"
    $sessionLog = Get-TodaySessionLog -SessionsDir $sessionsDir

    $sessionLogStatus = if ($null -eq $sessionLog) {
        "❌ No session log found for today"
    }
    else {
        "✅ Session log exists: $($sessionLog.Name)"
    }

    # Inject context (non-blocking)
    $output = @"

## Session Initialization Status

**Current Branch**: ``$currentBranch`` ✅
**Session Log**: $sessionLogStatus

### Git Status
``````
$gitStatus
``````

### Recent Commits
``````
$recentCommits
``````

---

**Session Start Hook**: Completed successfully
**Branch Protection**: Passed (not on main/master)
**Next Step**: $(if ($null -eq $sessionLog) { "Create session log with /session-init or Initialize-SessionLog.ps1" } else { "Continue with work" })

"@

    Write-Output $output
    exit 0
}
catch {
    # Fail-open on errors (don't block session startup)
    Write-Warning "Session initialization enforcer error: $($_.Exception.Message)"
    exit 0
}
