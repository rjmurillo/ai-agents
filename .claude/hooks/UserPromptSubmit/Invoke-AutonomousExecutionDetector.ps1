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
        '\bauto-',
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

    # Extract user prompt
    if (-not $hookInput.prompt) {
        exit 0
    }

    $userPrompt = $hookInput.prompt

    # Test for autonomy keywords
    if (-not (Test-AutonomyKeywords -Prompt $userPrompt)) {
        # No autonomy keywords detected
        exit 0
    }

    # Autonomy keywords detected - inject stricter protocol
    $output = @"

## ⚠️  AUTONOMOUS EXECUTION DETECTED

You have signaled autonomous/unattended execution. This mode enforces STRICTER protocol:

### Session Log Requirement (MANDATORY)
- Must have session log for today (`.agents/sessions/$(Get-Date -Format 'yyyy-MM-dd')-session-NN.json`)
- Session log must evidence memory retrieval (Serena activation, HANDOFF.md read)
- Session log must evidence all major decisions

### Multi-Agent Consensus Gates
High-risk operations REQUIRE multi-agent review BEFORE execution:
- PR merge, force push, branch delete
- Database migrations
- Infrastructure changes
- Config changes affecting production

Use `/orchestrator` to engage consensus gates.

### Audit Trail Requirements
Autonomous execution MUST log:
- Reason for autonomy request
- Decision rationale (from session log)
- Review gates passed/bypassed
- Exact commands executed
- Outcomes and any failures

### Blocked Operations in Autonomous Mode
These operations are BLOCKED in autonomous execution:
- \`\`\`git push --force\`\`\`
- \`\`\`git branch -D <branch>\`\`\`
- \`\`\`gh pr merge --delete-branch\`\`\`
- Any operation on \`main\` branch
- Any operation affecting CI/CD workflows

### Proceed Only If:
1. ✅ Session log exists with full evidence
2. ✅ All decisions logged in session
3. ✅ High-risk operations will use consensus gates
4. ✅ You understand audit trail requirements

**This is not a block - proceed at your own risk if requirements aren't met.**

See: ``.agents/SESSION-PROTOCOL.md`` for full autonomous execution protocol.

"@

    Write-Output $output
    exit 0
}
catch {
    # Fail-open on errors
    Write-Warning "Autonomous execution detector error: $($_.Exception.Message)"
    exit 0
}
