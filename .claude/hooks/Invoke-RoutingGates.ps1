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

    # Validate working directory assumption (required for Windows where CLAUDE_PROJECT_DIR is unavailable)
    # The hook invocation pattern uses Get-Location to resolve paths, which assumes CWD is project root
    $ProjectIndicators = @('.claude/settings.json', '.git')
    $IsValidProjectRoot = $false
    foreach ($indicator in $ProjectIndicators) {
        if (Test-Path (Join-Path (Get-Location) $indicator)) {
            $IsValidProjectRoot = $true
            break
        }
    }
    if (-not $IsValidProjectRoot) {
        Write-Warning "Invoke-RoutingGates: CWD '$(Get-Location)' does not appear to be a project root (missing .claude/settings.json or .git). Failing open."
        exit 0
    }
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
        Write-Warning "Invoke-RoutingGates: Failed to parse input JSON. Error: $_. Assuming empty command and allowing action."
        $Command = ''
    }

    <#
    .SYNOPSIS
        Writes hook failure events to persistent audit log.

    .DESCRIPTION
        Records hook failures (infrastructure errors, permission issues) to
        .claude/hooks/audit.log for investigation. Per Copilot #2679880646,
        fail-open scenarios should be logged for visibility.

    .PARAMETER Message
        The audit message to log.

    .PARAMETER HookName
        Name of the hook that failed.

    .EXAMPLE
        Write-HookAuditLog -HookName "RoutingGates" -Message "Permission denied: $($_.Exception.Message)"
    #>
    function Write-HookAuditLog {
        param(
            [Parameter(Mandatory)]
            [string]$Message,

            [Parameter(Mandatory)]
            [string]$HookName
        )

        try {
            $scriptDir = $PSScriptRoot
            if ([string]::IsNullOrWhiteSpace($scriptDir)) {
                $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
            }

            $auditLogPath = Join-Path $scriptDir "audit.log"
            $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            $logEntry = "[$timestamp] [$HookName] $Message"

            Add-Content -Path $auditLogPath -Value $logEntry -ErrorAction SilentlyContinue
        }
        catch {
            # Silently fail - don't block hook operation if audit logging fails
        }
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
            # Get list of changed files in committed branch changes (vs base)
            # SECURITY: Must check committed changes, not working tree, to prevent bypass
            # via uncommitted docs masking committed code changes
            $ChangedFiles = & git diff --name-only origin/main...HEAD 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Invoke-RoutingGates: git diff origin/main...HEAD failed (exit $LASTEXITCODE). Trying fallback."
                # Fallback to simple comparison if three-dot syntax fails
                $ChangedFiles = & git diff --name-only origin/main 2>&1
                if ($LASTEXITCODE -ne 0) {
                    Write-Warning "Invoke-RoutingGates: git diff origin/main also failed (exit $LASTEXITCODE). Failing open."
                    return $true
                }
            }

            if (-not $ChangedFiles) {
                # No changes detected, allow (fail-open)
                return $true
            }

            # Check if all changed files are documentation-only
            # Force to array to handle single-item case
            # SECURITY: Patterns must be anchored to prevent substring matches
            # (e.g., src/license_validator.cs must not match LICENSE)
            $CodeFiles = @(
                $ChangedFiles | Where-Object {
                    $_ -notmatch '\.md$' -and
                    $_ -notmatch '\.txt$' -and
                    $_ -notmatch '(^|/)README$' -and
                    $_ -notmatch '(^|/)LICENSE$' -and
                    $_ -notmatch '(^|/)CHANGELOG$' -and
                    $_ -notmatch '\.gitignore$'
                }
            )

            return ($CodeFiles.Count -eq 0)
        }
        catch [System.UnauthorizedAccessException] {
            # Permission error - likely temporary, fail-open
            $errorMsg = "Permission denied checking git diff: $($_.Exception.Message)"
            Write-Warning "Invoke-RoutingGates: $errorMsg. Failing open."
            Write-HookAuditLog -HookName "RoutingGates" -Message $errorMsg
            return $true
        }
        catch [System.IO.IOException] {
            # I/O error (disk, network) - infrastructure issue, fail-open
            $errorMsg = "I/O error checking git diff: $($_.Exception.Message)"
            Write-Warning "Invoke-RoutingGates: $errorMsg. Failing open."
            Write-HookAuditLog -HookName "RoutingGates" -Message $errorMsg
            return $true
        }
        catch {
            # Unexpected error during file filtering - log type for debugging
            $errorMsg = "Unexpected error checking changed files: $($_.Exception.GetType().Name) - $($_.Exception.Message)"
            Write-Warning "Invoke-RoutingGates: $errorMsg. Failing open."
            Write-HookAuditLog -HookName "RoutingGates" -Message $errorMsg
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
