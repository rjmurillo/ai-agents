<#
.SYNOPSIS
    Enforces ADR-007 Memory-First Architecture on user prompts.

.DESCRIPTION
    Claude Code hook that checks user prompts for planning/implementation keywords
    and injects a memory-first reminder when detected. Receives JSON input via stdin
    containing the prompt text.
    Part of the ADR-007 enforcement mechanism (Issue #729).

.PARAMETER InputObject
    JSON input from stdin containing the prompt text.

.NOTES
    Hook Type: UserPromptSubmit
    Exit Codes:
        0 = Success, stdout added to Claude's context
        2 = Block prompt (not used here)

.LINK
    .agents/architecture/ADR-007-memory-first-architecture.md
    .agents/SESSION-PROTOCOL.md
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromPipeline = $true)]
    [string]$InputObject
)

begin {
    Set-StrictMode -Version Latest
    $ErrorActionPreference = 'Stop'
    $AllInput = [System.Collections.ArrayList]::new()
}

process {
    if ($InputObject) {
        [void]$AllInput.Add($InputObject)
    }
}

end {
    # Join all pipeline input
    $InputJson = $AllInput -join "`n"

    # Extract prompt text from JSON
    $PromptText = ''
    try {
        $InputData = $InputJson | ConvertFrom-Json -ErrorAction SilentlyContinue
        if ($InputData.prompt) {
            $PromptText = $InputData.prompt
        }
    }
    catch {
        # If JSON parsing fails, use raw input
        $PromptText = $InputJson
    }

    # Keywords that suggest planning or implementation work
    $PlanningKeywords = @(
        'plan', 'implement', 'design', 'architect', 'build',
        'create', 'refactor', 'fix', 'add', 'update',
        'feature', 'issue', 'pr'
    )

    # Check if prompt contains any planning/implementation keywords
    $MatchFound = $false
    foreach ($Keyword in $PlanningKeywords) {
        if ($PromptText -match "(?i)\b$Keyword\b") {
            $MatchFound = $true
            break
        }
    }

    if ($MatchFound) {
        @"

**ADR-007 Memory Check**: Before proceeding with this task:

- Query ``memory-index`` for task-relevant memories
- Check Forgetful for cross-project patterns if applicable
- Evidence memory retrieval in session log

"@
    }

    exit 0
}
