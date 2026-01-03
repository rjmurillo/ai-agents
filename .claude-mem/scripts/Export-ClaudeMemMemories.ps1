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

    Exports all observations to: .claude-mem/memories/2026-01-03-all-memories.json

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
    Write-Error "Install the claude-mem plugin first"
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

# Ensure output file is in memories directory
if (-not $OutputFile.StartsWith($MemoriesDir)) {
    Write-Warning "Output file should be in .claude-mem/memories/ for version control"
}

Write-Host "🔍 Exporting Claude-Mem observations..." -ForegroundColor Cyan
Write-Host "   Query: '$Query'" -ForegroundColor Gray
Write-Host "   Output: $OutputFile" -ForegroundColor Gray
Write-Host ""

try {
    npx tsx $PluginScript $Query $OutputFile

    if (Test-Path $OutputFile) {
        $FileSize = (Get-Item $OutputFile).Length
        Write-Host ""
        Write-Host "✅ Export complete: $OutputFile ($FileSize bytes)" -ForegroundColor Green
        Write-Host ""
        Write-Host "⚠️  REQUIRED: Security review before commit" -ForegroundColor Yellow
        Write-Host "   Run: pwsh scripts/Review-MemoryExportSecurity.ps1 -ExportFile $OutputFile" -ForegroundColor Yellow
    }
    else {
        Write-Warning "Export file not created. Check query matches observations."
        exit 1
    }
}
catch {
    Write-Error "Export failed: $_"
    exit 1
}
