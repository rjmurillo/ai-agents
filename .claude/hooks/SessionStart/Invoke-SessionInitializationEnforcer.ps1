<#
.SYNOPSIS
    Enforces session protocol initialization at session start.

.DESCRIPTION
    Claude Code SessionStart hook that provides BLOCKING protection against
    working on main/master branches and injects git state into Claude's context.

    Checks:
    1. Current branch is not main/master (BLOCKING if violated)
    2. Git status and recent commits (injected into context)
    3. Session log status for today (reported, not blocking)

    Part of Tier 1 enforcement hooks (Session initialization).

.NOTES
    Hook Type: SessionStart
    Exit Codes:
        0 = Allow (not on protected branch)
        2 = Block (on main/master branch)

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

function Test-ProtectedBranch {
    param([string]$Branch)

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
    $projectDir = Get-ProjectDirectory
    $currentBranch = Get-CurrentBranch

    # BLOCKING: Check if on protected branch
    if (Test-ProtectedBranch -Branch $currentBranch) {
        $output = @"

## ⛔ BLOCKED: Cannot Work on Protected Branch

**YOU MUST switch to a feature branch before starting work.**

**Current Branch**: ``$currentBranch``

### Why This Matters
- Direct commits to main/master violate workflow policy
- All work must go through PR review
- Protected branches are for integration only

### How to Fix

Create or switch to a feature branch:

``````bash
# Create new feature branch
git checkout -b feat/your-feature-name

# Or switch to existing branch
git checkout existing-branch-name

# Or use worktrunk
wt switch feat/your-feature-name --create
``````

**This is a BLOCKING error. Session cannot proceed on $currentBranch.**

"@
        Write-Output $output
        Write-Error "Blocked: Cannot work on protected branch '$currentBranch'"
        exit 2
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
