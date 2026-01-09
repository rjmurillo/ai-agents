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

function Write-BlockResponse {
    param([string]$Reason)

    $response = @{
        decision = "block"
        reason = $Reason
    } | ConvertTo-Json -Compress

    Write-Output $response
    exit 2
}

function Get-WorkingDirectory {
    param($HookInput)

    if (-not [string]::IsNullOrWhiteSpace($HookInput.cwd)) {
        return $HookInput.cwd
    }
    if (-not [string]::IsNullOrWhiteSpace($env:CLAUDE_PROJECT_DIR)) {
        return $env:CLAUDE_PROJECT_DIR
    }
    return Get-Location
}

try {
    if (-not [Console]::IsInputRedirected) {
        exit 0
    }

    $inputJson = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($inputJson)) {
        exit 0
    }

    $hookInput = $inputJson | ConvertFrom-Json -ErrorAction Stop
    $cwd = Get-WorkingDirectory -HookInput $hookInput

    $previousLocation = Get-Location
    try {
        Set-Location $cwd

        # Critical: git branch --show-current fails (LASTEXITCODE != 0) if:
        # - Not in a git repository
        # - Detached HEAD state (during rebase, checkout of commit SHA)
        # - Git binary not found or execution error
        # We block operations in these cases because we cannot verify branch safety.
        $gitOutput = git branch --show-current 2>&1

        if ($LASTEXITCODE -eq 128) {
            # Fatal error: not a git repository
            Write-Error "Branch protection: Not a git repository in '$cwd'"
            Write-BlockResponse "Not a git repository or git not installed in '$cwd'. Cannot verify branch safety. Check: git status"
        }
        elseif ($LASTEXITCODE -ne 0) {
            # Other git errors
            Write-Error "Branch protection: git command failed (exit $LASTEXITCODE) in '$cwd': $gitOutput"
            Write-BlockResponse "Cannot determine current git branch in '$cwd' (git failed with exit code $LASTEXITCODE). Verify manually: git branch --show-current. Output: $gitOutput"
        }

        $currentBranch = $gitOutput.Trim()
        $protectedBranches = @('main', 'master')

        if ($currentBranch -in $protectedBranches) {
            Write-BlockResponse "Cannot commit or push directly to protected branch '$currentBranch'. Create a feature branch first: git checkout -b feature/your-feature-name"
        }

        exit 0
    }
    finally {
        Set-Location $previousLocation
    }
}
catch {
    $errorMsg = "Branch protection check failed in '$cwd': $($_.Exception.Message)"
    Write-Error $errorMsg
    Write-BlockResponse "Branch protection check failed and cannot verify branch safety in '$cwd'. Verify manually: git branch --show-current. Error: $($_.Exception.Message)"
}
