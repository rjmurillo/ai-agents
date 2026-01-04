#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Export complete claude-mem institutional knowledge backup

.DESCRIPTION
    Exports ALL claude-mem data (observations, sessions, summaries, prompts)
    across ALL projects (default) or scoped to a single project.

    For disaster recovery, onboarding, or fresh instance setup.

    Security review is AUTOMATIC and BLOCKING - violations prevent commit.

.PARAMETER Project
    Optional project filter (e.g., "ai-agents"). If omitted, exports ALL projects.

.PARAMETER OutputFile
    Override default filename. Default: .claude-mem/memories/backup-YYYY-MM-DD-HHMM.json

.EXAMPLE
    pwsh .claude-mem/scripts/Export-ClaudeMemFullBackup.ps1
    # Exports ALL projects
    # Creates: .claude-mem/memories/backup-YYYY-MM-DD-HHMM.json

.EXAMPLE
    pwsh .claude-mem/scripts/Export-ClaudeMemFullBackup.ps1 -Project "ai-agents"
    # Exports single project
    # Creates: .claude-mem/memories/backup-YYYY-MM-DD-HHMM-ai-agents.json

.EXAMPLE
    pwsh .claude-mem/scripts/Export-ClaudeMemFullBackup.ps1 -OutputFile custom-backup.json
    # Custom output path

.NOTES
    CRITICAL: This script calls the Claude-Mem export plugin using an FTS query of ".".
    The underlying plugin currently treats an empty query as "match nothing", returning 0 rows.
    Using "." forces a non-empty FTS query that, in practice, matches all indexed content, but it
    still relies on the plugin's FTS behavior and may not include non-indexed data.
    For a guaranteed complete, non-FTS backup, prefer the direct export script provided by this
    project instead of relying solely on this FTS-based convenience wrapper.

    See Export-ClaudeMemDirect.ps1 for 100% complete SQLite-based export.

    Security review runs automatically and blocks commit if violations found.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$Project,

    [Parameter(Mandatory = $false)]
    [string]$OutputFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Locate plugin script
$PluginScript = Join-Path $env:HOME '.claude' 'plugins' 'marketplaces' 'thedotmack' 'scripts' 'export-memories.ts'

if (-not (Test-Path $PluginScript)) {
    Write-Error "Claude-Mem plugin script not found at: $PluginScript"
    Write-Error "Install the claude-mem plugin first"
    exit 1
}

# Generate default filename
$MemoriesDir = Join-Path $PSScriptRoot '..' 'memories'
$Timestamp = Get-Date -Format 'yyyy-MM-dd-HHmm'
$DefaultFile = "backup-$Timestamp"
if ($Project) { $DefaultFile += "-$Project" }
$DefaultFile += ".json"

$OutputPath = if ($OutputFile) { $OutputFile } else {
    Join-Path $MemoriesDir $DefaultFile
}

# Ensure memories directory exists
if (-not (Test-Path $MemoriesDir)) {
    New-Item -ItemType Directory -Path $MemoriesDir -Force | Out-Null
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
$NormalizedOutput = [System.IO.Path]::GetFullPath($OutputPath)
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

# Build plugin script arguments
# Use "." as query to match all observations via search
# For direct database export without search, use Export-ClaudeMemDirect.ps1
$PluginArgs = @(".", $OutputPath)
if ($Project) {
    $PluginArgs += "--project=$Project"
}

Write-Host "🔍 Exporting full claude-mem backup..." -ForegroundColor Cyan
Write-Host "   Query: . (matches all data)" -ForegroundColor Gray
if ($Project) {
    Write-Host "   Scope: Project '$Project'" -ForegroundColor Gray
} else {
    Write-Host "   Scope: ALL projects" -ForegroundColor Gray
}
Write-Host "   Output: $OutputPath" -ForegroundColor Gray
Write-Host ""

# Call plugin script
npx tsx $PluginScript @PluginArgs

# Verify export and display stats
if (Test-Path $OutputPath) {
    $Data = Get-Content $OutputPath | ConvertFrom-Json
    $FileSize = (Get-Item $OutputPath).Length

    Write-Host ""
    Write-Host "✅ Full backup created: $OutputPath" -ForegroundColor Green
    Write-Host "   File size: $([math]::Round($FileSize / 1KB, 2)) KB" -ForegroundColor Gray
    Write-Host ""
    Write-Host "📊 Exported:" -ForegroundColor Cyan
    Write-Host "   Observations: $($Data.totalObservations)"
    Write-Host "   Sessions: $($Data.totalSessions)"
    Write-Host "   Summaries: $($Data.totalSummaries)"
    Write-Host "   Prompts: $($Data.totalPrompts)"

    # Check for empty export
    $TotalRecords = $Data.totalObservations + $Data.totalSessions + $Data.totalSummaries + $Data.totalPrompts
    if ($TotalRecords -eq 0) {
        Write-Host ""
        Write-Host "⚠️  Empty Export" -ForegroundColor Yellow
        Write-Host "   No data found in claude-mem database"
        if ($Project) {
            Write-Host "   Try without -Project to check other projects"
        } else {
            Write-Host "   Database may be new or data hasn't been stored yet"
        }
    }

    # Automatic security review (BLOCKING - pit of success)
    Write-Host ""
    Write-Host "🔒 Running security review..." -ForegroundColor Cyan
    $SecurityScript = Join-Path $PSScriptRoot '..' '..' 'scripts' 'Review-MemoryExportSecurity.ps1'

    & $SecurityScript -ExportFile $OutputPath
    $SecurityExitCode = $LASTEXITCODE  # Capture immediately to prevent stale exit code

    if ($SecurityExitCode -ne 0) {
        Write-Host ""
        Write-Error "Security review FAILED. Violations must be fixed before commit."
        exit 1
    }

    Write-Host "✅ Security review PASSED" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next Steps:" -ForegroundColor Cyan
    Write-Host "  Import on fresh instance: pwsh .claude-mem/scripts/Import-ClaudeMemMemories.ps1"
} else {
    Write-Error "Export failed: Output file not created"
    exit 1
}
