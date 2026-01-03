#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Import Claude-Mem memory snapshots from .claude-mem/memories/

.DESCRIPTION
    Idempotent import of all JSON memory files. See .claude-mem/memories/AGENTS.md for details.

.EXAMPLE
    pwsh scripts/Import-ClaudeMemMemories.ps1
#>

$ErrorActionPreference = 'Stop'
$MemoriesDir = Join-Path $PSScriptRoot '..' '.claude-mem' 'memories'

if (-not (Test-Path $MemoriesDir)) {
    Write-Host "No memories directory found. Creating: $MemoriesDir" -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $MemoriesDir -Force | Out-Null
    exit 0
}

$Files = Get-ChildItem -Path $MemoriesDir -Filter '*.json' -File
if ($Files.Count -eq 0) {
    Write-Host "No memory files to import" -ForegroundColor Cyan
    exit 0
}

Write-Host "Importing $($Files.Count) memory file(s)..." -ForegroundColor Green

foreach ($File in $Files) {
    Write-Host "  $($File.Name)" -ForegroundColor Gray
    npx tsx "$PSScriptRoot/import-memories.ts" $File.FullName 2>&1 | Out-Null
}

Write-Host "Import complete (duplicates skipped automatically)" -ForegroundColor Green
