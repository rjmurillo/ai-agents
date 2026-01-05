<#
.SYNOPSIS
    Blocks git commit/push operations on main/master branches.

.DESCRIPTION
    Claude Code PreToolUse hook that prevents accidental commits and pushes
    to protected branches (main, master). This enforces the SESSION-PROTOCOL
    requirement that work must be done on feature branches.

    Part of the hooks expansion implementation (Issue #773, Phase 1).

.NOTES
    Hook Type: PreToolUse
    Matcher: Bash(git commit*|git push*)
    Exit Codes:
        0 = Success, operation allowed
        2 = Block operation (on protected branch)

.LINK
    .agents/SESSION-PROTOCOL.md
    .agents/analysis/claude-code-hooks-opportunity-analysis.md
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

try {
    # Parse hook input from stdin (JSON)
    $hookInput = $null
    if (-not [Console]::IsInputRedirected) {
        # No input provided, allow operation
        exit 0
    }

    $inputJson = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($inputJson)) {
        exit 0
    }

    $hookInput = $inputJson | ConvertFrom-Json -ErrorAction Stop

    # Get current working directory
    $cwd = $hookInput.cwd
    if ([string]::IsNullOrWhiteSpace($cwd)) {
        $cwd = $env:CLAUDE_PROJECT_DIR
    }
    if ([string]::IsNullOrWhiteSpace($cwd)) {
        $cwd = Get-Location
    }

    # Get current branch
    $previousLocation = Get-Location
    try {
        Set-Location $cwd

        $currentBranch = git branch --show-current 2>&1
        if ($LASTEXITCODE -ne 0) {
            # Not in a git repo or git command failed, allow operation
            exit 0
        }

        $currentBranch = $currentBranch.Trim()

        # Check if on protected branch
        $protectedBranches = @('main', 'master')
        if ($currentBranch -in $protectedBranches) {
            # Block the operation - output JSON decision
            $blockResponse = @{
                decision = "block"
                reason = "Cannot commit or push directly to protected branch '$currentBranch'. Create a feature branch first: git checkout -b feature/your-feature-name"
            } | ConvertTo-Json -Compress

            Write-Output $blockResponse

            # Exit code 2 blocks the operation
            exit 2
        }

        # Not on protected branch, allow operation
        exit 0
    }
    finally {
        Set-Location $previousLocation
    }
}
catch {
    # On error, allow operation (fail open for non-blocking behavior)
    Write-Warning "Branch protection check failed: $($_.Exception.Message)"
    exit 0
}
