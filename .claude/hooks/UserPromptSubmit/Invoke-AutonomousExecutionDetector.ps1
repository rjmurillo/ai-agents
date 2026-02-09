<#
.SYNOPSIS
    Injects stricter protocol enforcement for autonomy keywords.

.DESCRIPTION
    Claude Code UserPromptSubmit hook that detects keywords signaling
    autonomous execution (e.g., "autonomous", "hands-off", "without asking").

    When detected, injects stricter protocol guards into context:
    - Requires explicit session log evidence
    - Enforces multi-agent consensus gates
    - Injects audit trail requirements
    - Blocks high-risk operations (merge, delete)

    This prevents accidental autonomous failures by making protocol
    requirements explicit before execution begins.

    Part of Tier 2 enforcement hooks (Issue #773, Autonomous safety).

.NOTES
    Hook Type: UserPromptSubmit
    Exit Codes:
        0 = Success (context injected or keywords not detected)
        2 = Block on critical failure only (rare)

    EXIT CODE SEMANTICS (Claude Hook Convention):
    Exit code 0 always (educational injection, not blocking).

.LINK
    .agents/SESSION-PROTOCOL.md
    .agents/governance/PROJECT-CONSTRAINTS.md
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Import shared hook utilities
Import-Module "$PSScriptRoot/../Common/HookUtilities.psm1" -Force

function Test-AutonomyKeywords {
    param([string]$Prompt)

    if ([string]::IsNullOrWhiteSpace($Prompt)) {
        return $false
    }

    # Keywords signaling autonomous/unattended execution
    $keywords = @(
        '\bautonomous\b',
        '\bhands-off\b',
        '\bwithout asking\b',
        '\bwithout confirmation\b',
        '\bauto-\w+',  # Matches auto-execute, auto-run, etc. (Copilot #2678558284, #2678584221)
        '\bunattended\b',
        '\brun autonomously\b',
        '\bfull autonomy\b',
        '\bno human\b',
        '\bno verification\b',
        '\bblindly\b'
    )

    foreach ($keyword in $keywords) {
        if ($Prompt -match $keyword) {
            return $true
        }
    }

    return $false
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

    # Extract user prompt with fallback for schema variations (Copilot #2678558292)
    $userPrompt = $null
    if ($hookInput.prompt) {
        $userPrompt = $hookInput.prompt
    }
    elseif ($hookInput.user_message_text) {
        $userPrompt = $hookInput.user_message_text
    }
    elseif ($hookInput.message) {
        $userPrompt = $hookInput.message
    }

    if ([string]::IsNullOrWhiteSpace($userPrompt)) {
        exit 0
    }

    # Test for autonomy keywords
    if (-not (Test-AutonomyKeywords -Prompt $userPrompt)) {
        # No autonomy keywords detected
        exit 0
    }

    # Autonomy keywords detected - inject compact stricter protocol
    Write-Output "`nAutonomous mode: Stricter protocol active. Session log with evidence required. High-risk ops (merge, force-push, branch delete) need consensus gates via /orchestrator. Blocked on main. See SESSION-PROTOCOL.md.`n"
    exit 0
}
catch {
    # Fail-open on errors
    Write-Warning "Autonomous execution detector error: $($_.Exception.Message)"
    exit 0
}
