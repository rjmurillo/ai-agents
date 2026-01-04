#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Export Claude-Mem memory snapshots to .claude-mem/memories/

.DESCRIPTION
    Exports matching Claude-Mem observations to JSON file for version control and team sharing.

    IMPORTANT: Security review is REQUIRED before committing exports to git.
    Run: pwsh scripts/Review-MemoryExportSecurity.ps1 -ExportFile [file].json

    See .claude-mem/memories/README.md for complete workflow documentation.

.PARAMETER Query
    Search query to filter memories. Empty string exports all observations.

.PARAMETER OutputFile
    Path to output JSON file. Defaults to .claude-mem/memories/YYYY-MM-DD-session-NNN.json

    Naming convention: YYYY-MM-DD-session-NNN-topic.json

.PARAMETER SessionNumber
    Optional session number for default filename. If not specified, uses current date only.

.PARAMETER Topic
    Optional topic for default filename (e.g., "frustrations", "testing-philosophy")

.EXAMPLE
    pwsh .claude-mem/scripts/Export-ClaudeMemMemories.ps1 -Query "session 229" -SessionNumber 229 -Topic "frustrations"

    Exports to: .claude-mem/memories/2026-01-03-session-229-frustrations.json

.EXAMPLE
    pwsh .claude-mem/scripts/Export-ClaudeMemMemories.ps1 -Query "testing" -OutputFile .claude-mem/memories/testing-learnings.json

.EXAMPLE
    pwsh .claude-mem/scripts/Export-ClaudeMemMemories.ps1 -Query "" -Topic "all-memories"

    Exports all observations matching query criteria (empty query may include project/date filters)
    to: .claude-mem/memories/2026-01-03-all-memories.json

.NOTES
    Calls the claude-mem plugin export script directly at:
    ~/.claude/plugins/marketplaces/thedotmack/scripts/export-memories.ts

    SECURITY: Always review exports before committing:
    - Run scripts/Review-MemoryExportSecurity.ps1
    - Check for API keys, passwords, tokens, secrets
    - Verify no private file paths or PII
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [AllowEmptyString()]
    [ValidatePattern('^[a-zA-Z0-9\s\-_.,()]*$')]
    [string]$Query,

    [Parameter(Mandatory = $false)]
    [string]$OutputFile,

    [Parameter(Mandatory = $false)]
    [int]$SessionNumber,

    [Parameter(Mandatory = $false)]
    [string]$Topic
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$MemoriesDir = Join-Path $PSScriptRoot '..' 'memories'
$PluginScript = Join-Path $env:HOME '.claude' 'plugins' 'marketplaces' 'thedotmack' 'scripts' 'export-memories.ts'

if (-not (Test-Path $PluginScript)) {
    Write-Error "Claude-Mem plugin script not found at: $PluginScript"
    Write-Error ""
    Write-Error "Install the claude-mem plugin:"
    Write-Error "  1. Visit: https://github.com/thedotmack/claude-mem"
    Write-Error "  2. Follow installation instructions for Claude Code MCP plugins"
    exit 1
}

# Ensure memories directory exists
if (-not (Test-Path $MemoriesDir)) {
    Write-Host "Creating memories directory: $MemoriesDir" -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $MemoriesDir -Force | Out-Null
}

# Generate default filename if not specified
if (-not $OutputFile) {
    $Date = Get-Date -Format 'yyyy-MM-dd'

    $FilenameParts = @($Date)

    if ($SessionNumber) {
        $FilenameParts += "session-$SessionNumber"
    }

    if ($Topic) {
        $FilenameParts += $Topic
    }

    $Filename = ($FilenameParts -join '-') + '.json'
    $OutputFile = Join-Path $MemoriesDir $Filename
}

# Ensure output file is in memories directory (prevent path traversal - CWE-22)
# WHY: Normalize paths before comparison to prevent directory traversal attacks
# SECURITY: GetFullPath() resolves ".." and ensures paths are absolute
#
# ATTACK SCENARIO: Without this check, an attacker could specify:
#   -OutputFile "../../etc/passwd" or "../../../sensitive-data.json"
# This would write export data outside the intended directory, potentially:
#   - Overwriting system files
#   - Exposing sensitive data to unintended locations
#   - Bypassing access controls
#
# VALID: .claude-mem/memories/export.json
# INVALID: .claude-mem/../export.json (resolves outside memories dir)
$NormalizedOutput = [System.IO.Path]::GetFullPath($OutputFile)
$NormalizedDir = [System.IO.Path]::GetFullPath($MemoriesDir)
# Add trailing separator to prevent "memories-evil" directory bypass
$NormalizedDirWithSep = $NormalizedDir.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (-not $NormalizedOutput.StartsWith($NormalizedDirWithSep, [System.StringComparison]::OrdinalIgnoreCase)) {
    Write-Error "Path traversal attempt detected. Output file must be inside '$MemoriesDir' directory."
    Write-Error ""
    Write-Error "Attempted path: $OutputFile"
    Write-Error "Normalized path: $NormalizedOutput"
    Write-Error "Required parent: $NormalizedDir"
    Write-Error ""
    Write-Error "Valid example: .claude-mem/memories/export.json"
    Write-Error "Invalid example: ../export.json (escapes memories directory)"
    exit 1
}

Write-Host "🔍 Exporting Claude-Mem observations..." -ForegroundColor Cyan
Write-Host "   Query: '$Query'" -ForegroundColor Gray
Write-Host "   Output: $OutputFile" -ForegroundColor Gray
Write-Host ""

try {
    # SECURITY: Quote all variables to prevent command injection (CWE-77)
    # WHY: Unquoted variables allow shell metacharacters to inject commands
    npx tsx "$PluginScript" "$Query" "$OutputFile"

    # Check exit code to detect plugin failures
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Export plugin failed with exit code: $LASTEXITCODE"
        Write-Error ""
        Write-Error "Troubleshooting:"
        Write-Error "  1. Verify plugin is properly installed at: $PluginScript"
        Write-Error "  2. Check database connection and permissions"
        Write-Error "  3. Verify query syntax: '$Query'"
        Write-Error "  4. Check disk space availability"
        Write-Error "  5. Review plugin logs for detailed errors"
        exit $LASTEXITCODE
    }

    # Validate file was created AND is fresh (not stale from previous run)
    if (Test-Path $OutputFile) {
        $FileInfo = Get-Item $OutputFile
        $FileSize = $FileInfo.Length
        $FileAge = (Get-Date) - $FileInfo.LastWriteTime

        # File must be less than 1 minute old to be considered fresh
        if ($FileAge.TotalMinutes -gt 1) {
            Write-Error "Export file exists but is stale (last modified: $($FileInfo.LastWriteTime))"
            Write-Error "Plugin may have failed silently. Delete old file and retry."
            exit 1
        }

        # File must have content
        if ($FileSize -eq 0) {
            Write-Error "Export file created but is empty (0 bytes)"
            Write-Error "Query may not match any observations: '$Query'"
            exit 1
        }

        Write-Host ""
        Write-Host "✅ Export complete: $OutputFile ($FileSize bytes)" -ForegroundColor Green
        Write-Host ""

        # SECURITY GATE: Automatically run security review
        $SecurityScript = Join-Path $PSScriptRoot '..' '..' 'scripts' 'Review-MemoryExportSecurity.ps1'
        if (Test-Path $SecurityScript) {
            Write-Host "🔒 Running mandatory security review..." -ForegroundColor Cyan
            Write-Host ""

            & $SecurityScript -ExportFile $OutputFile

            if ($LASTEXITCODE -ne 0) {
                Write-Host ""
                Write-Error "Security review FAILED. Sensitive data detected in export."
                Write-Error "DO NOT commit this file until review passes."
                Write-Error ""
                Write-Error "Next steps:"
                Write-Error "  1. Review and redact sensitive data in: $OutputFile"
                Write-Error "  2. Re-run: pwsh $SecurityScript -ExportFile $OutputFile"
                Write-Error "  3. Only commit after review passes"
                exit 1
            }

            Write-Host ""
            Write-Host "✅ Security review PASSED - Safe to commit" -ForegroundColor Green
        }
        else {
            Write-Host "⚠️  WARNING: Security review script not found at: $SecurityScript" -ForegroundColor Yellow
            Write-Host "   Manually review for sensitive data before committing" -ForegroundColor Yellow
        }
    }
    else {
        Write-Error "Export file not created despite successful exit code."
        Write-Error "Query may not match any observations: '$Query'"
        Write-Error ""
        Write-Error "Troubleshooting:"
        Write-Error "  1. Verify query matches existing observations"
        Write-Error "  2. Check project filter settings in plugin"
        Write-Error "  3. Review date range filters"
        exit 1
    }
}
catch {
    Write-Error "Export failed: $($_.Exception.Message)"
    Write-Error ""
    Write-Error "Script state at failure:"
    Write-Error "  Query: '$Query'"
    Write-Error "  Output file: $OutputFile"
    Write-Error "  Plugin script: $PluginScript"
    Write-Error "  Working directory: $PWD"
    Write-Error ""
    Write-Error "Stack trace:"
    Write-Error $_.ScriptStackTrace
    exit 1
}
