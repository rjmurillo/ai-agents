#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Import Claude-Mem memory snapshots from .claude-mem/memories/

.DESCRIPTION
    Idempotent import of all JSON memory files from the memories directory.
    Automatically prevents duplicates using composite keys.

    See .claude-mem/memories/README.md for complete workflow documentation.

.EXAMPLE
    pwsh .claude-mem/scripts/Import-ClaudeMemMemories.ps1

.NOTES
    Calls the claude-mem plugin import script directly at:
    ~/.claude/plugins/marketplaces/thedotmack/scripts/import-memories.ts
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$MemoriesDir = Join-Path $PSScriptRoot '..' 'memories'
$PluginScript = Join-Path $env:HOME '.claude' 'plugins' 'marketplaces' 'thedotmack' 'scripts' 'import-memories.ts'

if (-not (Test-Path $PluginScript)) {
    Write-Error "Claude-Mem plugin script not found at: $PluginScript"
    Write-Error "Install the claude-mem plugin first"
    exit 1
}

if (-not (Test-Path $MemoriesDir)) {
    Write-Host "No memories directory found at: $MemoriesDir" -ForegroundColor Yellow
    Write-Host "Creating directory..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $MemoriesDir -Force | Out-Null
    Write-Host "No memory files to import" -ForegroundColor Cyan
    exit 0
}

$Files = @(Get-ChildItem -Path $MemoriesDir -Filter '*.json' -File)
if ($Files.Count -eq 0) {
    Write-Host "No memory files to import from: $MemoriesDir" -ForegroundColor Cyan
    exit 0
}

Write-Host "🔄 Importing $($Files.Count) memory file(s) from .claude-mem/memories/" -ForegroundColor Green
Write-Host ""

$ImportCount = 0
foreach ($File in $Files) {
    Write-Host "  📁 $($File.Name)" -ForegroundColor Gray

    try {
        npx tsx $PluginScript $File.FullName 2>&1 | Out-Null
        $ImportCount++
    }
    catch {
        Write-Warning "Failed to import $($File.Name): $_"
    }
}

Write-Host ""
Write-Host "✅ Import complete: $ImportCount file(s) processed" -ForegroundColor Green
Write-Host "   Duplicates automatically skipped via composite key matching" -ForegroundColor Gray
