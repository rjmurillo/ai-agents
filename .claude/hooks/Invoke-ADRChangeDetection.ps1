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
    Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
}

$DetectScript = Join-Path $ProjectRoot ".claude/skills/adr-review/scripts/Detect-ADRChanges.ps1"

# Skip if detection script doesn't exist
if (-not (Test-Path $DetectScript)) {
    exit 0
}

try {
    # Run detection script
    $result = & $DetectScript -BasePath $ProjectRoot -IncludeUntracked | ConvertFrom-Json

    if ($result.HasChanges) {
        $output = @"

## ADR Changes Detected - Review Required

**BLOCKING GATE**: ADR changes detected - invoke /adr-review before commit

### Changes Found

"@
        if ($result.Created.Count -gt 0) {
            $output += "**Created**: $($result.Created -join ', ')`n"
        }
        if ($result.Modified.Count -gt 0) {
            $output += "**Modified**: $($result.Modified -join ', ')`n"
        }
        if ($result.Deleted.Count -gt 0) {
            $output += "**Deleted**: $($result.Deleted -join ', ')`n"
        }

        $output += @"

### Required Action

Invoke the adr-review skill for multi-agent consensus:

``````text
/adr-review [ADR-path]
``````

This ensures 6-agent debate (architect, critic, independent-thinker, security, analyst, high-level-advisor) before ADR acceptance.

**Skill**: ``.claude/skills/adr-review/SKILL.md``

"@

        Write-Output $output
    }
    # No output if no changes - don't clutter context
}
catch {
    # Non-blocking - detection failure shouldn't stop session
    # Silently continue
}

exit 0
