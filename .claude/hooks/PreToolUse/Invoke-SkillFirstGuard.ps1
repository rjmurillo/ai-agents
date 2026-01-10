<#
.SYNOPSIS
    Blocks raw `gh` commands when validated skill scripts exist.

.DESCRIPTION
    Claude Code PreToolUse hook that enforces skills-first mandate by blocking
    raw `gh` CLI commands when a tested, validated skill script exists for that
    operation. This prevents:

    - Duplicated logic across sessions
    - Untested inline commands
    - Inconsistent error handling
    - Loss of reusable abstractions

    Uses two-stage skill discovery:
    1. Exact mapping via hardcoded operation->action table
    2. Fuzzy matching via filesystem scan (fallback)

    Part of Tier 2 enforcement hooks (Issue #773, Skills-first mandate).

.NOTES
    Hook Type: PreToolUse
    Matcher: Bash
    Exit Codes:
        0 = Allow (not a gh command, or no skill exists)
        2 = Block (skill exists, must use it)

    EXIT CODE SEMANTICS (Claude Hook Convention):
    Exit code 2 signals BLOCKING. Claude interprets this as "stop processing
    and show user the reason."

.LINK
    .serena/memories/usage-mandatory.md
    .claude/skills/github/SKILL.md
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Import shared hook utilities
Import-Module "$PSScriptRoot/../Common/HookUtilities.psm1" -Force

function Write-BlockResponse {
    param(
        [string]$BlockedCommand,
        [string]$SkillPath,
        [string]$ExampleUsage
    )

    $output = @"

## ⛔ BLOCKED: Raw GitHub Command Detected

**YOU MUST use the validated skill script instead of raw ``gh`` commands.**

### Blocked Command
``````
$BlockedCommand
``````

### Required Alternative (Copy-Paste Ready)
``````powershell
$ExampleUsage
``````

**Why Skills Are Mandatory**:
- ✅ Tested with Pester (100% coverage)
- ✅ Structured error handling
- ✅ Consistent output format
- ✅ Centrally maintained
- ❌ Raw ``gh`` commands: None of the above

**Evidence**: Session 15 (2025-12-18) had 5+ violations in one session, dropping success rate to 42%. Skills-first mandate created same day with BLOCKING enforcement.

**This is not optional.** See: ``.serena/memories/usage-mandatory.md``

"@
    Write-Output $output
    # Use Console.Error to avoid exception from Write-Error with Stop action preference
    [Console]::Error.WriteLine("Blocked: Raw gh command detected. Use skill at $SkillPath")
    exit 2
}

function Test-GhCommand {
    param([string]$Command)

    if ([string]::IsNullOrWhiteSpace($Command)) {
        return $null
    }

    # Match: gh <operation> <action> ...
    if ($Command -match '\bgh\s+(\w+)\s+(\w+)') {
        return @{
            Operation = $Matches[1]
            Action = $Matches[2]
            FullCommand = $Command
        }
    }

    return $null
}

function Get-SkillScript {
    param(
        [string]$Operation,
        [string]$Action,
        [string]$ProjectDir
    )

    # Stage 1: Exact mapping (hardcoded)
    $skillMappings = @{
        'pr' = @{
            'view'    = @{ Script = 'Get-PRContext.ps1'; Example = 'pwsh .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest 123' }
            'list'    = @{ Script = 'Get-PullRequests.ps1'; Example = 'pwsh .claude/skills/github/scripts/pr/Get-PullRequests.ps1' }
            'create'  = @{ Script = 'New-PR.ps1'; Example = 'pwsh .claude/skills/github/scripts/pr/New-PR.ps1 -Title "..." -Body "..."' }
            'comment' = @{ Script = 'Post-PRCommentReply.ps1'; Example = 'pwsh .claude/skills/github/scripts/pr/Post-PRCommentReply.ps1 -PullRequest 123 -Body "..."' }
            'merge'   = @{ Script = 'Merge-PR.ps1'; Example = 'pwsh .claude/skills/github/scripts/pr/Merge-PR.ps1 -PullRequest 123' }
            'close'   = @{ Script = 'Close-PR.ps1'; Example = 'pwsh .claude/skills/github/scripts/pr/Close-PR.ps1 -PullRequest 123' }
            'checks'  = @{ Script = 'Get-PRChecks.ps1'; Example = 'pwsh .claude/skills/github/scripts/pr/Get-PRChecks.ps1 -PullRequest 123' }
        }
        'issue' = @{
            'view'    = @{ Script = 'Get-IssueContext.ps1'; Example = 'pwsh .claude/skills/github/scripts/issue/Get-IssueContext.ps1 -Issue 456' }
            'create'  = @{ Script = 'New-Issue.ps1'; Example = 'pwsh .claude/skills/github/scripts/issue/New-Issue.ps1 -Title "..." -Body "..."' }
            'comment' = @{ Script = 'Post-IssueComment.ps1'; Example = 'pwsh .claude/skills/github/scripts/issue/Post-IssueComment.ps1 -Issue 456 -Body "..."' }
            'list'    = @{ Script = 'Get-Issues.ps1'; Example = 'pwsh .claude/skills/github/scripts/issue/Get-Issues.ps1' }
        }
    }

    # Check exact mapping first
    if ($skillMappings.ContainsKey($Operation)) {
        $actions = $skillMappings[$Operation]
        if ($actions.ContainsKey($Action)) {
            $mapping = $actions[$Action]
            $scriptPath = Join-Path $ProjectDir ".claude" "skills" "github" "scripts" $Operation $mapping.Script
            if (Test-Path $scriptPath) {
                return @{
                    Path = $scriptPath
                    Example = $mapping.Example
                }
            }
        }
    }

    # Stage 2: Fuzzy matching (fallback)
    $searchPath = Join-Path $ProjectDir ".claude" "skills" "github" "scripts" $Operation
    if (-not (Test-Path $searchPath)) {
        return $null
    }

    $matchingScripts = @(Get-ChildItem -Path $searchPath -Filter "*$Action*.ps1" -ErrorAction SilentlyContinue)
    if ($matchingScripts.Count -gt 0) {
        $script = $matchingScripts[0]
        $relativePath = ".claude/skills/github/scripts/$Operation/$($script.Name)"
        return @{
            Path = $script.FullName
            Example = "pwsh $relativePath [parameters]"
        }
    }

    return $null
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

    # Test if this is a gh command
    $ghCommand = Test-GhCommand -Command $command
    if ($null -eq $ghCommand) {
        # Not a gh command, allow
        exit 0
    }

    # Check if skill exists for this operation
    $projectDir = Get-ProjectDirectory
    $skill = Get-SkillScript -Operation $ghCommand.Operation -Action $ghCommand.Action -ProjectDir $projectDir

    if ($null -eq $skill) {
        # No skill exists, fail-open (allow new capabilities)
        exit 0
    }

    # Skill exists - BLOCK with educational message
    Write-BlockResponse `
        -BlockedCommand $ghCommand.FullCommand `
        -SkillPath $skill.Path `
        -ExampleUsage $skill.Example
}
catch {
    # Fail-open on errors (don't block on infrastructure issues)
    Write-Warning "Skill-first guard error: $($_.Exception.Message)"
    exit 0
}
