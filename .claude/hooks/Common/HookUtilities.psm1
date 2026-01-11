<#
.SYNOPSIS
    Shared utilities for Claude Code hook scripts.

.DESCRIPTION
    Provides common functions used across multiple hook types to eliminate
    code duplication and ensure consistent behavior.

.NOTES
    This module is automatically imported by hook scripts that need these functions.
    All functions are exported and available after Import-Module.

.LINK
    Issue #859 - Copilot review comments: DRY violations
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-ProjectDirectory {
    <#
    .SYNOPSIS
        Resolves the project root directory.

    .DESCRIPTION
        Returns the project root by checking CLAUDE_PROJECT_DIR environment
        variable first, then walking up from script location to find .git directory.

    .OUTPUTS
        String - Project root directory path, or $null if not found.

    .EXAMPLE
        $projectDir = Get-ProjectDirectory
        if ($projectDir) {
            $sessionsDir = Join-Path $projectDir ".agents" "sessions"
        }
    #>
    if (-not [string]::IsNullOrWhiteSpace($env:CLAUDE_PROJECT_DIR)) {
        return $env:CLAUDE_PROJECT_DIR
    }

    # Walk up from current location to find .git
    try {
        $currentPath = Get-Location | Select-Object -ExpandProperty Path
        $currentDir = Get-Item $currentPath
        while ($null -ne $currentDir) {
            if (Test-Path (Join-Path $currentDir.FullName ".git")) {
                return $currentDir.FullName
            }
            $currentDir = $currentDir.Parent
        }
    }
    catch {
        Write-Warning "Failed to locate project directory: $($_.Exception.Message)"
    }

    return $null
}

function Test-GitCommitCommand {
    <#
    .SYNOPSIS
        Tests if a command string is a git commit command.

    .DESCRIPTION
        Checks if the command contains "git commit" or "git ci" to identify
        commit operations that need enforcement.

        Matches both "commit" and "ci" because "git ci" is a widely-used
        alias for "git commit" in many developer workflows (Copilot #2678558269, #2678558289).

    .PARAMETER Command
        The command string to test.

    .OUTPUTS
        Boolean - $true if command is git commit, $false otherwise.

    .EXAMPLE
        if (Test-GitCommitCommand -Command $hookInput.tool_input.command) {
            # Apply commit-time validations
        }

    .NOTES
        Both "git commit" and "git ci" are matched intentionally to support
        common aliases. This ensures hooks trigger consistently regardless of
        user's git configuration.
    #>
    param([string]$Command)

    if ([string]::IsNullOrWhiteSpace($Command)) {
        return $false
    }

    return $Command -match '(?:^|\s)git\s+(commit|ci)'
}

function Get-TodaySessionLog {
    <#
    .SYNOPSIS
        Finds the most recent session log for a specific date.

    .DESCRIPTION
        Searches the sessions directory for JSON session logs matching the specified
        date pattern (YYYY-MM-DD-session-*.json) and returns the most recent one.

    .PARAMETER SessionsDir
        Path to the .agents/sessions directory.

    .PARAMETER Date
        The date to search for in YYYY-MM-DD format. If not provided, uses current date.
        Pass this parameter to avoid midnight race conditions (Copilot #2679880612).

    .OUTPUTS
        FileInfo object for the most recent session log, or $null if none found.

    .EXAMPLE
        $today = Get-Date -Format 'yyyy-MM-dd'
        $sessionLog = Get-TodaySessionLog -SessionsDir ".agents/sessions" -Date $today
        if ($sessionLog) {
            $content = Get-Content $sessionLog.FullName -Raw | ConvertFrom-Json
        }
    #>
    param(
        [Parameter(Mandatory)]
        [string]$SessionsDir,

        [string]$Date = (Get-Date -Format "yyyy-MM-dd")
    )

    if (-not (Test-Path $SessionsDir)) {
        Write-Warning "Session directory not found: $SessionsDir"
        return $null
    }

    try {
        $logs = @(Get-ChildItem -Path $SessionsDir -Filter "$Date-session-*.json" -File -ErrorAction Stop)
    }
    catch {
        Write-Warning "Failed to read session logs from $SessionsDir : $($_.Exception.Message)"
        return $null
    }

    if ($logs.Count -eq 0) {
        return $null
    }

    return $logs | Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

function Get-TodaySessionLogs {
    <#
    .SYNOPSIS
        Finds all session logs for today's date.

    .DESCRIPTION
        Searches the sessions directory for all JSON session logs matching today's
        date pattern (YYYY-MM-DD-session-*.json) and returns them as an array.

    .PARAMETER SessionsDir
        Path to the .agents/sessions directory.

    .OUTPUTS
        Array of FileInfo objects for today's session logs, or empty array if none found.

    .EXAMPLE
        $sessionLogs = Get-TodaySessionLogs -SessionsDir ".agents/sessions"
        if ($sessionLogs.Count -gt 0) {
            $latestLog = $sessionLogs | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        }
    #>
    param([string]$SessionsDir)

    if (-not (Test-Path $SessionsDir)) {
        Write-Warning "Session directory not found: $SessionsDir"
        return @()
    }

    $today = Get-Date -Format "yyyy-MM-dd"

    try {
        $logs = @(Get-ChildItem -Path $SessionsDir -Filter "$today-session-*.json" -File -ErrorAction Stop)
    }
    catch {
        Write-Warning "Failed to read session logs from $SessionsDir : $($_.Exception.Message)"
        return @()
    }

    return $logs
}

# Export all functions
Export-ModuleMember -Function Get-ProjectDirectory, Test-GitCommitCommand, Get-TodaySessionLog, Get-TodaySessionLogs
