<#
.SYNOPSIS
    Routing-level enforcement gates for Claude Code per ADR-033.

.DESCRIPTION
    Blocks high-stakes actions until validation prerequisites are met.
    Implements Gate 2: QA Validation Gate that blocks PR creation without QA evidence.

    QA Evidence is satisfied by:
    1. QA report exists in .agents/qa/ from the last 24 hours
    2. QA section in today's session log

    Bypass conditions:
    - Documentation-only PRs (no code changes)
    - SKIP_QA_GATE environment variable set

.PARAMETER InputObject
    JSON input from stdin containing the tool invocation details.

.NOTES
    Hook Type: PreToolUse

    EXIT CODES (Claude Hook Semantics - exempt from ADR-035):
        0 = Allow action OR JSON decision (deny/allow)
        1 = Hook error (fail-open)
        2 = Block action immediately (hook-specific)

    Per ADR-033, this uses JSON decision mode for structured error messages.
    Claude Code hooks are exempt from ADR-035 exit code standardization
    because Claude interprets these codes with special semantics.
    See ADR-035 section "Claude Code Hook Exit Codes" for details.

.LINK
    .agents/architecture/ADR-033-routing-level-enforcement-gates.md
    .agents/architecture/ADR-035-exit-code-standardization.md
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
    # Join all pipeline input and parse JSON
    $InputJson = $AllInput -join "`n"
    $Command = ''

    try {
        $InputData = $InputJson | ConvertFrom-Json -ErrorAction Stop
        if ($InputData.tool_input -and $InputData.tool_input.command) {
            $Command = $InputData.tool_input.command
        }
    }
    catch {
        # If JSON parsing fails, treat as empty command (fail-open)
        $Command = ''
    }

    <#
    .SYNOPSIS
        Gets today's session log file.

    .DESCRIPTION
        Searches .agents/sessions/ for a session log matching today's date.

    .OUTPUTS
        System.IO.FileInfo or $null
    #>
    function Get-TodaySessionLog {
        $SessionDir = ".agents/sessions"
        $Today = Get-Date -Format "yyyy-MM-dd"

        if (Test-Path $SessionDir) {
            $SessionLog = Get-ChildItem -Path $SessionDir -Filter "$Today*-session-*.md" |
                Sort-Object Name -Descending |
                Select-Object -First 1
            return $SessionLog
        }
        return $null
    }

    <#
    .SYNOPSIS
        Tests whether QA evidence exists.

    .DESCRIPTION
        Checks for QA evidence in two places:
        1. QA report files in .agents/qa/ modified within the last 24 hours
        2. QA-related sections in today's session log

    .OUTPUTS
        System.Boolean - $true if QA evidence exists, $false otherwise.
    #>
    function Test-QAEvidence {
        # Option 1: QA report exists in .agents/qa/ from last 24 hours
        $QADir = ".agents/qa"
        if (Test-Path $QADir) {
            $CutoffTime = (Get-Date).AddHours(-24)
            $Reports = Get-ChildItem -Path $QADir -Filter "*.md" -File |
                Where-Object { $_.LastWriteTime -gt $CutoffTime }
            if ($Reports) {
                return $true
            }
        }

        # Option 2: QA section in session log
        $SessionLog = Get-TodaySessionLog
        if ($SessionLog) {
            $Content = Get-Content $SessionLog.FullName -Raw -ErrorAction SilentlyContinue
            if ($Content) {
                # Check for QA-related sections in session log
                if ($Content -match '(?i)## QA|qa agent|Test Results|QA Validation|Test Strategy') {
                    return $true
                }
            }
        }

        return $false
    }

    <#
    .SYNOPSIS
        Tests whether the current changes are documentation-only.

    .DESCRIPTION
        Uses git diff to check if only documentation files (.md) have been modified.
        Returns true if no code files have been changed.

    .OUTPUTS
        System.Boolean - $true if docs-only, $false otherwise.
    #>
    function Test-DocumentationOnly {
        try {
            # Get list of changed files staged or in working tree
            $ChangedFiles = & git diff --name-only HEAD 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $ChangedFiles) {
                # Try comparing against origin/main if HEAD comparison fails
                $ChangedFiles = & git diff --name-only origin/main 2>$null
            }

            if (-not $ChangedFiles) {
                # No changes detected, allow (fail-open)
                return $true
            }

            # Check if all changed files are documentation-only
            # Force to array to handle single-item case
            $CodeFiles = @(
                $ChangedFiles | Where-Object {
                    $_ -notmatch '\.md$' -and
                    $_ -notmatch '\.txt$' -and
                    $_ -notmatch 'README' -and
                    $_ -notmatch 'LICENSE' -and
                    $_ -notmatch 'CHANGELOG' -and
                    $_ -notmatch '\.gitignore$'
                }
            )

            return ($CodeFiles.Count -eq 0)
        }
        catch {
            # On error, fail-open (allow)
            return $true
        }
    }

    # Gate 2: QA Validation (for PR creation)
    # Per ADR-033 Phase 2 specification
    if ($Command -like "*gh pr create*") {
        # Check for bypass conditions

        # Bypass 1: Environment variable override
        if ($env:SKIP_QA_GATE -eq 'true') {
            # Silently allow - bypass is intentional
            exit 0
        }

        # Bypass 2: Documentation-only changes
        if (Test-DocumentationOnly) {
            # Allow docs-only PRs without QA
            exit 0
        }

        # Main check: QA evidence required
        if (-not (Test-QAEvidence)) {
            $Output = @{
                decision = "deny"
                reason = @"
QA VALIDATION GATE: QA evidence required before PR creation.

Invoke the QA agent to verify changes:
  #runSubagent with subagentType=qa prompt='Verify changes for PR'

Or create a QA report file in .agents/qa/

Bypass conditions:
- Documentation-only PRs (auto-detected based on file extensions)
- Set SKIP_QA_GATE=true environment variable (requires justification)
"@
            }
            $Output | ConvertTo-Json -Compress
            exit 0  # JSON output with deny decision
        }
    }

    # All gates passed
    exit 0
}
