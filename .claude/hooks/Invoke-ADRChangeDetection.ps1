<#
.SYNOPSIS
    Detects ADR file changes and prompts Claude to invoke adr-review skill.

.DESCRIPTION
    Claude Code hook that checks for ADR file changes at session start.
    When changes are detected, outputs a blocking gate message that prompts
    Claude to invoke the adr-review skill for multi-agent consensus.

.NOTES
    Hook Type: SessionStart
    Exit Codes:
        0 = Success, stdout added to Claude's context
        2 = Block session (not used - detection is advisory)

.LINK
    .claude/skills/adr-review/SKILL.md
    .agents/architecture/ADR-*.md
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Get project root from environment or derive from script location
$ProjectRoot = if ($env:CLAUDE_PROJECT_DIR) {
    $env:CLAUDE_PROJECT_DIR
} else {
    Write-Verbose "CLAUDE_PROJECT_DIR not set, deriving from script location"
    Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
}

# Validate the resolved path is a git repository
if (-not (Test-Path (Join-Path $ProjectRoot ".git"))) {
    Write-Warning "ADR detection: ProjectRoot '$ProjectRoot' is not a git repository"
    exit 0
}

$DetectScript = Join-Path $ProjectRoot ".claude/skills/adr-review/scripts/Detect-ADRChanges.ps1"

# Skip if detection script doesn't exist
if (-not (Test-Path $DetectScript)) {
    exit 0
}

try {
    # Run detection script and capture output
    $scriptOutput = & $DetectScript -BasePath $ProjectRoot -IncludeUntracked 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "ADR detection script exited with code $LASTEXITCODE"
        Write-Warning "Output: $scriptOutput"
        exit 0  # Non-blocking, but logged
    }
    $result = $scriptOutput | ConvertFrom-Json

    if ($result.HasChanges) {
        $message = @"

## ADR Changes Detected - Review Required

**BLOCKING GATE**: ADR changes detected - invoke /adr-review before commit

### Changes Found

"@
        if ($result.Created.Count -gt 0) {
            $message += "**Created**: $($result.Created -join ', ')`n"
        }
        if ($result.Modified.Count -gt 0) {
            $message += "**Modified**: $($result.Modified -join ', ')`n"
        }
        if ($result.Deleted.Count -gt 0) {
            $message += "**Deleted**: $($result.Deleted -join ', ')`n"
        }

        $message += @"

### Required Action

Invoke the adr-review skill for multi-agent consensus:

``````text
/adr-review [ADR-path]
``````

This ensures 6-agent debate (architect, critic, independent-thinker, security, analyst, high-level-advisor) before ADR acceptance.

**Skill**: ``.claude/skills/adr-review/SKILL.md``

"@

        Write-Output $message
    }
    # No output if no changes - don't clutter context
}
catch {
    # Non-blocking - detection failure shouldn't stop session
    # But log the error for debuggability
    Write-Warning "ADR change detection failed: $($_.Exception.Message)"
    Write-Warning "ADR detection skipped. Run detection manually if needed:"
    Write-Warning "  pwsh .claude/skills/adr-review/scripts/Detect-ADRChanges.ps1"
}

exit 0
