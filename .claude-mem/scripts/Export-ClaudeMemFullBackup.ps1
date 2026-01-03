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
    CRITICAL: Uses query="." as workaround for plugin bug where empty query returns 0 results.
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

# Build plugin script arguments
# CRITICAL: Use "." as query (empty string is BROKEN in plugin)
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

    if ($LASTEXITCODE -ne 0) {
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
